"""
OCR 결과 텍스트에서 키워드 목록을 만드는 어댑터.

- 기본: Kiwi 형태소(명사) + 영어 단어 후보 (외부 LLM 비용 없음)
- `kiwipiepy` 미설치 시 한글은 정규식·빈도 기반 fallback
- 키워드 후보마다 조사 토큰 제거 후처리(Kiwi 태그 기반, 미설치 시 접미사 휴리스틱)

LLM 기반 추출은 `clova_ocr_service.CLOVAOCRService.process_file` 내 주석으로 보존.
"""
from __future__ import annotations

import os
import re
try:
    from kiwipiepy import Kiwi  # type: ignore
except Exception:  # pragma: no cover
    Kiwi = None

_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-\']{1,}")

# Kiwi 세종 품사: 조사·접속 조사 계열 (명사만 남길 때 제외)
_JOSA_TAGS = frozenset(
    {
        "JKS",
        "JKC",
        "JKG",
        "JKO",
        "JKB",
        "JKQ",
        "JX",
        "JC",
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


def _strip_josa_kiwi(kiwi, word: str) -> str:
    """단일 키워드 후보에서 조사 토큰을 제거하고 이어 붙인다."""
    if not word or len(word) < 2:
        return word
    parts: list[str] = []
    for sent in kiwi.analyze(word, normalize_coda=True):
        tokens = sent[0] if isinstance(sent, (list, tuple)) and sent else []
        for tok in tokens:
            tag = getattr(tok, "tag", "") or ""
            if tag in _JOSA_TAGS:
                continue
            form = (getattr(tok, "form", "") or "").strip()
            if form:
                parts.append(form)
        break
    merged = "".join(parts).strip()
    return merged if len(merged) >= 1 else word


# Kiwi 미설치·실패 시: 붙은 OCR 덩어리(예: 단어를)만 보수적으로 정리 (긴 접미사 먼저)
_JOSA_SUFFIX_LONG = (
    "으로서",
    "이라고",
    "에서부터",
    "으로",
    "에서",
    "부터",
    "까지",
    "처럼",
    "만큼",
    "이랑",
    "하고",
    "이라",
)
_JOSA_SUFFIX_ONE = ("은", "는", "을", "를", "이", "가", "과", "와", "도", "만", "로")


def _strip_josa_fallback_regex(word: str) -> str:
    if len(word) < 3:
        return word
    w = word
    for suf in _JOSA_SUFFIX_LONG:
        if w.endswith(suf):
            rest = w[: -len(suf)]
            if len(rest) >= 2:
                return rest
            return w
    for suf in _JOSA_SUFFIX_ONE:
        if w.endswith(suf):
            rest = w[:-1]
            if len(rest) >= 2:
                return rest
            return w
    return w


def _strip_josa(kiwi, word: str) -> str:
    if kiwi is not None:
        return _strip_josa_kiwi(kiwi, word)
    return _strip_josa_fallback_regex(word)


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
    return [w for w, _ in items[: max(0, top_k)]]


def _extract_korean_nouns_kiwi(text: str, top_k: int, kiwi) -> list[str]:
    if not text:
        return []
    freq: dict[str, int] = {}
    for sent in kiwi.analyze(text, normalize_coda=True):
        tokens = sent[0] if isinstance(sent, (list, tuple)) and sent else []
        for tok in tokens:
            form = getattr(tok, "form", "") or ""
            tag = getattr(tok, "tag", "") or ""
            if tag not in ("NNG", "NNP"):
                continue
            w = form.strip()
            if len(w) < 2:
                continue
            if w in _KO_STOPWORDS:
                continue
            if len(w) > 24:
                continue
            freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in items[: max(0, top_k)]]


def _extract_korean_candidates_fallback(text: str, top_k: int) -> list[str]:
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
        if w in _KO_STOPWORDS:
            continue
        if len(w) > 24:
            continue
        freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in items[: max(0, top_k)]]


def extract_keywords_from_text(
    text: str,
    *,
    top_k_korean: int = 40,
    top_k_english: int = 30,
) -> list[str]:
    """
    OCR 페이지 텍스트 → 키워드 문자열 리스트 (한글 명사 위주 + 영어 단어).
    """
    max_chars = int(os.getenv("OCR_KEYWORDS_MAX_CHARS", "20000"))
    safe_text = text or ""
    if max_chars > 0 and len(safe_text) > max_chars:
        safe_text = safe_text[:max_chars]

    en = _extract_english_candidates(safe_text, top_k=top_k_english)

    ko: list[str]
    if Kiwi is not None:
        try:
            kiwi = Kiwi()
            ko = _extract_korean_nouns_kiwi(safe_text, top_k=top_k_korean, kiwi=kiwi)
        except Exception:
            ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean)
    else:
        ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean)

    seen: set[str] = set()
    out: list[str] = []
    for w in ko + en:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out
