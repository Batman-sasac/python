"""
OCR 결과 텍스트에서 키워드 목록을 만드는 어댑터.

- 기본: Kiwi 형태소(명사) + 연속 명사/접사 재결합(복합어) + 영어 단어 후보
- 복합어: NNG/NNP 연속 구간과 명사 접사(XSN: 적·성·화 등)를 원문과 대조해 한 덩어리로 복원
- `kiwipiepy` 미설치 시 한글은 정규식·빈도 기반 fallback
- 키워드 후보마다 `service.josa_strip`으로 조사 제거

LLM 기반 추출은 `clova_ocr_service.CLOVAOCRService.process_file` 내 주석으로 보존.
"""
from __future__ import annotations

import os
import re
import logging

from service.josa_strip import strip_josa

try:
    from kiwipiepy import Kiwi  # type: ignore
except Exception:  # pragma: no cover
    Kiwi = None

logger = logging.getLogger(__name__)
_BACKEND_LOGGED = False

_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-\']{1,}")
_WS_RE = re.compile(r"\s+")
# 붙어 있으면 한 덩어리(100), 사이에 글자/공백이 있으면 각각(1, 2) — 원문 기준
_NUMBER_SPAN_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
_DIGIT_ONLY_RE = re.compile(r"^[\d,\.]+$")
# 원문 span에 있으면 복합어 후보에서 제외 (줄바꿈·구두점 등)
_COMPOUND_SPAN_BREAK_RE = re.compile(r"[\n\r\t,;:\(\)\[\]{}·|/\\<>\"'`!?…]")

# Kiwi XSN 중 복합 명사를 이루는 접사 (과목·도메인 공통)
_COMPOUND_XSN_FORMS = frozenset(
    {
        "적",
        "성",
        "화",
        "식",
        "률",
        "력",
        "형",
        "겹",
        "용",
        "도",
        "점",
        "량",
        "자",
    }
)

_KO_STOPWORDS = {
    "것",
    "수",
    "등",
    "및",
    "대한",
    "통해",
    "관련",
    "경우",
    "때",
    "중",
    "전",
    "후",
    "이번",
    "다음",
    "위",
    "아래",
    "그",
    "이",
    "저",
    "또",
    "그리고",
    "하지만",
    "또는",
    "때문",
}

# 형태소 분석기(Kiwi) 없이 regex fallback을 쓸 때,
# 동사/형용사 원형(…다)이나 서술어 계열이 섞이는 것을 줄이기 위한 휴리스틱 필터.
_KO_VERBLIKE_SUFFIXES = (
    "하다",
    "되다",
    "이다",
    "있다",
    "없다",
    "같다",
)


def _is_verb_like_fallback(word: str) -> bool:
    """
    Kiwi가 없을 때(=품사 태깅 불가) 조사 제거 후 토큰이 동사/형용사로 보이면 제외한다.
    - OCR 텍스트는 종종 '…했다/…된다/…이다' 같은 서술어를 그대로 포함한다.
    - 명사 키워드만 원하는 요구에 맞춰 보수적으로 필터링한다.
    """
    if not word:
        return False
    if word in _KO_VERBLIKE_SUFFIXES:
        return True
    for suf in _KO_VERBLIKE_SUFFIXES:
        if word.endswith(suf) and len(word) <= 12:
            return True
    # '…다'로 끝나는 짧은 어절은 서술어일 확률이 높다 (예: 빠르다, 넓다)
    if word.endswith("다") and len(word) <= 6:
        return True
    return False


_EN_STOPWORDS = {
    "the",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "for",
    "with",
    "as",
    "at",
    "by",
    "from",
    "an",
    "a",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "it",
    "this",
    "that",
    "these",
    "those",
}


def _appears_in_text(word: str, text: str) -> bool:
    w = (word or "").strip()
    return len(w) >= 2 and w in (text or "")


def _is_morpheme_mergeable(tag: str, form: str) -> bool:
    if tag in ("NNG", "NNP", "NR", "NNB"):
        return True
    if tag == "XSN" and form in _COMPOUND_XSN_FORMS:
        return True
    return False


def _compound_from_token_run(tokens) -> str:
    return "".join((getattr(t, "form", "") or "").strip() for t in tokens)


def _tokens_are_contiguous(text: str, run) -> bool:
    for i in range(len(run) - 1):
        prev_end = getattr(run[i], "start", 0) + getattr(run[i], "len", 0)
        next_start = getattr(run[i + 1], "start", 0)
        if next_start > prev_end and text[prev_end:next_start]:
            return False
    return True


def _keyword_from_token_run(text: str, run) -> str | None:
    if len(run) < 2:
        return None
    if not _tokens_are_contiguous(text, run):
        return None
    start = getattr(run[0], "start", None)
    end_tok = run[-1]
    end = getattr(end_tok, "start", None)
    length = getattr(end_tok, "len", None)
    if start is None or end is None or length is None:
        merged = _compound_from_token_run(run)
        return merged if _is_valid_korean_keyword(merged) and _appears_in_text(merged, text) else None
    span = text[start : end + length]
    if _COMPOUND_SPAN_BREAK_RE.search(span):
        return None
    cleaned = _WS_RE.sub("", span)
    if not _is_valid_korean_keyword(cleaned):
        return None
    return cleaned


def _iter_compound_runs(tokens, text: str):
    run: list = []
    pending_prefix = None

    def flush():
        nonlocal run, pending_prefix
        if len(run) >= 2:
            yielded = list(run)
            run.clear()
            pending_prefix = None
            return yielded
        run.clear()
        pending_prefix = None
        return None

    for tok in tokens:
        form = (getattr(tok, "form", "") or "").strip()
        tag = getattr(tok, "tag", "") or ""

        if tag == "XPN" and not run:
            pending_prefix = tok
            continue

        if _is_morpheme_mergeable(tag, form):
            if pending_prefix is not None:
                run.append(pending_prefix)
                pending_prefix = None
            if run and not _tokens_are_contiguous(text, run + [tok]):
                done = flush()
                if done:
                    yield done
            run.append(tok)
            continue

        done = flush()
        if done:
            yield done
        if tag == "XPN":
            pending_prefix = tok
        else:
            pending_prefix = None

    done = flush()
    if done:
        yield done


def _is_valid_korean_keyword(word: str) -> bool:
    if not word or len(word) < 2 or len(word) > 24:
        return False
    if word in _KO_STOPWORDS:
        return False
    return True


def _add_korean_freq(
    freq: dict[str, int],
    word: str,
    text: str,
    *,
    kiwi=None,
    strip: bool = True,
) -> None:
    w = (word or "").strip()
    if strip:
        w = strip_josa(kiwi, w)
    if not _is_valid_korean_keyword(w):
        return
    if not _appears_in_text(w, text):
        return
    freq[w] = freq.get(w, 0) + 1


def _has_independent_occurrence(short: str, long: str, text: str) -> bool:
    """short가 long의 부분 문자열이어도, text 안에서 long 밖에 solo로 있으면 True."""
    if not short or short not in long:
        return True
    idx = 0
    while True:
        pos = text.find(short, idx)
        if pos < 0:
            return False
        in_long = False
        lidx = 0
        while True:
            lpos = text.find(long, lidx)
            if lpos < 0:
                break
            if lpos <= pos < lpos + len(long):
                in_long = True
                break
            lidx = lpos + 1
        if not in_long:
            return True
        idx = pos + 1


def _select_top_korean(freq: dict[str, int], top_k: int, text: str) -> list[str]:
    """빈도·길이 순 정렬 후, 더 긴 키워드에 완전히 흡수된 부분 문자열만 제외. top_k<=0 이면 전체."""
    items = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    out: list[str] = []
    for w, _ in items:
        if any(
            w != sel and w in sel and not _has_independent_occurrence(w, sel, text)
            for sel in out
        ):
            continue
        out.append(w)
        if top_k > 0 and len(out) >= top_k:
            break
    return out


def _find_number_spans(text: str) -> list[str]:
    """원문에 연속으로 붙은 숫자만 통째로 추출. 떨어져 있으면 각각 별도 span."""
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _NUMBER_SPAN_RE.finditer(text):
        raw = m.group(0)
        if not raw or raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
    return out


def _filter_digit_fragment_keywords(words: list[str], text: str) -> list[str]:
    """
    형태소 경로에서 잘린 숫자 조각(100 → 1,0,0) 제거.
    원문에 더 긴 연속 숫자 span이 있으면 그 부분만 버리고, 떨어진 숫자는 유지.
    """
    spans = _find_number_spans(text)
    span_set = set(spans)

    out: list[str] = []
    for w in words:
        if not w:
            continue
        if not _DIGIT_ONLY_RE.match(w):
            out.append(w)
            continue
        if w in span_set:
            out.append(w)
            continue
        if any(w in s and w != s for s in spans):
            continue
        out.append(w)
    return out


def _extract_english_candidates(text: str, top_k: int) -> list[str]:
    if not text:
        return []
    words = _EN_WORD_RE.findall(text)
    if not words:
        return []
    freq: dict[str, int] = {}
    for w in words:
        ww = w.lower().strip("-'")
        if len(ww) < 2 or len(ww) > 24:
            continue
        if ww in _EN_STOPWORDS:
            continue
        freq[ww] = freq.get(ww, 0) + 1
    items = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    if top_k <= 0:
        return [w for w, _ in items]
    return [w for w, _ in items[:top_k]]


def _extract_korean_nouns_kiwi(text: str, top_k: int, kiwi) -> list[str]:
    if not text:
        return []
    freq: dict[str, int] = {}
    for sent in kiwi.analyze(text, normalize_coda=True):
        tokens = sent[0] if isinstance(sent, (list, tuple)) and sent else []
        for run in _iter_compound_runs(tokens, text):
            compound = _keyword_from_token_run(text, run)
            if compound:
                freq[compound] = freq.get(compound, 0) + 1
        for tok in tokens:
            form = getattr(tok, "form", "") or ""
            tag = getattr(tok, "tag", "") or ""
            if tag not in ("NNG", "NNP"):
                continue
            w = strip_josa(kiwi, form.strip())
            _add_korean_freq(freq, w, text, kiwi=kiwi, strip=False)
    return _select_top_korean(freq, top_k, text)


def _extract_korean_candidates_fallback(text: str, top_k: int, kiwi) -> list[str]:
    if not text:
        return []
    tokens = re.findall(r"[가-힣]{2,}", text)
    if not tokens:
        return []
    freq: dict[str, int] = {}
    for t in tokens:
        w = t.strip()
        if not w:
            continue
        w = strip_josa(kiwi, w)
        if not w or len(w) < 2:
            continue
        if _is_verb_like_fallback(w):
            continue
        if w in _KO_STOPWORDS:
            continue
        if len(w) > 24:
            continue
        _add_korean_freq(freq, w, text, kiwi=kiwi, strip=False)
    return _select_top_korean(freq, top_k, text)


def extract_keywords_from_text(
    text: str,
    *,
    top_k_korean: int | None = None,
    top_k_english: int | None = None,
) -> list[str]:
    """
    OCR 페이지 텍스트 → 키워드 문자열 리스트 (한글 명사 위주 + 영어 단어).
    top_k_korean / top_k_english 가 None·0 이하면 해당 언어 키워드를 전부 반환한다.
    환경 변수 OCR_KEYWORDS_TOP_K_KOREAN / OCR_KEYWORDS_TOP_K_ENGLISH 로 기본 상한 조정 가능(0=전체).
    """
    global _BACKEND_LOGGED

    if top_k_korean is None:
        top_k_korean = int(os.getenv("OCR_KEYWORDS_TOP_K_KOREAN", "0"))
    if top_k_english is None:
        top_k_english = int(os.getenv("OCR_KEYWORDS_TOP_K_ENGLISH", "0"))

    max_chars = int(os.getenv("OCR_KEYWORDS_MAX_CHARS", "20000"))
    safe_text = text or ""
    if max_chars > 0 and len(safe_text) > max_chars:
        safe_text = safe_text[:max_chars]

    en = _extract_english_candidates(safe_text, top_k=top_k_english)

    ko: list[str]
    if Kiwi is not None:
        try:
            kiwi = Kiwi()
            if not _BACKEND_LOGGED:
                logger.info("[KW] backend=kiwi")
                _BACKEND_LOGGED = True
            ko = _extract_korean_nouns_kiwi(safe_text, top_k=top_k_korean, kiwi=kiwi)
        except Exception:
            if not _BACKEND_LOGGED:
                logger.info("[KW] backend=fallback (kiwi_init_or_analyze_failed)")
                _BACKEND_LOGGED = True
            ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean, kiwi=None)
    else:
        if not _BACKEND_LOGGED:
            logger.info("[KW] backend=fallback (kiwi_not_installed)")
            _BACKEND_LOGGED = True
        ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean, kiwi=None)

    numbers = _find_number_spans(safe_text)

    seen: set[str] = set()
    out: list[str] = []
    for w in numbers + ko + en:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)

    return _filter_digit_fragment_keywords(out, safe_text)
