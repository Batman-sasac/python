"""
OCR/키워드 후보 문자열에서 조사 토큰 제거.

- Kiwi 사용 시: 세종 품사로 조사(J*) 토큰만 제외 후 이어 붙임
- Kiwi 없음: 붙은 OCR 덩어리용 접미사 휴리스틱
"""

from __future__ import annotations

# Kiwi 세종 품사: 조사·접속 조사 계열
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

# Kiwi 미설치·실패 시: 긴 접미사 먼저
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


def strip_josa_kiwi(kiwi, word: str) -> str:
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


def strip_josa_fallback_regex(word: str) -> str:
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


def strip_josa(kiwi, word: str) -> str:
    """kiwi가 있으면 형태소 기반, 없으면 접미사 휴리스틱."""
    if kiwi is not None:
        return strip_josa_kiwi(kiwi, word)
    return strip_josa_fallback_regex(word)
