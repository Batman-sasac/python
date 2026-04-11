"""
OCR 결과 텍스트에서 키워드 목록을 만드는 어댑터.

- 기본: Kiwi 형태소(명사) + 영어 단어 후보 (외부 LLM 비용 없음)
- `kiwipiepy` 미설치 시 한글은 정규식·빈도 기반 fallback
- 키워드 후보마다 `service.josa_strip`으로 조사 제거

LLM 기반 추출은 `clova_ocr_service.CLOVAOCRService.process_file` 내 주석으로 보존.
"""
from __future__ import annotations

import os
import re

from service.josa_strip import strip_josa

try:
    from kiwipiepy import Kiwi  # type: ignore
except Exception:  # pragma: no cover
    Kiwi = None

_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-\']{1,}")

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
            w = strip_josa(kiwi, form.strip())
            if len(w) < 2:
                continue
            if w in _KO_STOPWORDS:
                continue
            if len(w) > 24:
                continue
            freq[w] = freq.get(w, 0) + 1
    items = sorted(freq.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))
    return [w for w, _ in items[: max(0, top_k)]]


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
            ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean, kiwi=None)
    else:
        ko = _extract_korean_candidates_fallback(safe_text, top_k=top_k_korean, kiwi=None)

    seen: set[str] = set()
    out: list[str] = []
    for w in ko + en:
        if w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out
