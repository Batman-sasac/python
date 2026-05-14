"""
복습 알림: APScheduler로 매 분 DB 확인 후 Expo Push API로 푸시 발송 (iOS 전용).
- ExponentPushToken만 사용 (expo-notifications).
- 발송 후 users.remind_sent_at 갱신(sent 처리)으로 같은 날 중복 발송 방지.
- DB remind_time 컬럼이 PostgreSQL time 타입이어도 정규화 후 비교.
"""
import logging
import re
import time
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import os

import httpx
import requests

from core.database import supabase

logger = logging.getLogger(__name__)


def _supabase_execute_with_connect_retry(request_builder, *, attempts: int = 4, base_delay: float = 0.8):
    """DNS·TCP 일시 실패(ConnectError 등) 시 지수 백오프로 재시도. 스케줄러 분 단위 호출에 맞춤."""
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return request_builder.execute()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            last = e
            if attempt + 1 >= attempts:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "Supabase 연결 실패, %.1fs 후 재시도 (%d/%d): %s",
                delay,
                attempt + 1,
                attempts,
                e,
            )
            time.sleep(delay)
    assert last is not None
    raise last

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def is_notification_simulation() -> bool:
    """DB 갱신 없이 알림 로직·스케줄러만 테스트할 때 True. env: NOTIFICATION_SIMULATE=1 또는 true"""
    v = (os.getenv("NOTIFICATION_SIMULATE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _is_expo_push_token(token: str) -> bool:
    """ExponentPushToken 형식이면 True. iOS/iPad용 Expo 푸시에 사용."""
    return bool(token and token.strip().startswith("ExponentPushToken["))


def _token_log_snippet(token: str, max_head: int = 40, max_tail: int = 12) -> str:
    """로그용 토큰 앞/뒤만 노출 (전체 토큰 노출 방지)."""
    if not token or len(token) <= max_head + max_tail:
        return "(빈 문자열)" if not token else f"len={len(token)}"
    return f"{token[:max_head]}...{token[-max_tail:]} (len={len(token)})"


def send_expo_notification(token: str, title: str, body: str) -> bool:
    """
    Expo Push API로 푸시 발송. iOS/iPad에서 ExponentPushToken 사용 시 필요.
    Firebase는 APNs 토큰을 받을 수 없어 iOS 기기에는 Expo API를 사용해야 함.
    """
    if is_notification_simulation():
        return True
    try:
        payload = {"to": token, "title": title, "body": body, "sound": "default"}
        resp = requests.post(
            EXPO_PUSH_URL,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        try:
            data = resp.json() if resp.content else {}
        except Exception:
            data = {}
        if data.get("data"):
            ticket = data["data"][0] if isinstance(data["data"], list) else data["data"]
            if ticket.get("status") == "error":
                msg = ticket.get("message", "unknown")
                logger.error(
                    "[Expo] 푸시 실패 | message=%s | token_snippet=%s",
                    msg,
                    _token_log_snippet(token),
                )
                return False
        return True
    except requests.RequestException as e:
        logger.exception(
            "[Expo] 전송 실패 | token_snippet=%s",
            _token_log_snippet(token),
        )
        return False
    except Exception as e:
        logger.exception(
            "[Expo] 예외 | token_snippet=%s",
            _token_log_snippet(token),
        )
        return False


def send_push_notification(token: str, title: str, body: str) -> bool:
    """
    Expo Push API로 푸시 발송 (iOS 전용, ExponentPushToken만 사용).
    """
    if not token or not token.strip():
        logger.warning("[Push] 발송 스킵: 토큰이 비어 있음")
        return False
    token = token.strip()
    if not _is_expo_push_token(token):
        logger.warning(
            "[Push] ExponentPushToken이 아님 — 발송 스킵 | snippet=%s",
            _token_log_snippet(token),
        )
        return False
    return send_expo_notification(token, title, body)


# remind_sent_at 컬럼 없을 때 에러 방지 (없으면 발송 기록 생략)
_remind_sent_at_available: bool | None = None


def _is_remind_sent_at_missing_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "remind_sent_at" in msg and ("does not exist" in msg or "42703" in msg)


def _normalize_remind_time(val: str | None) -> str:
    """
    DB remind_time을 HH:MM 형태로 통일 (KST 기준, leading zero 포함).
    - PostgreSQL time 타입: Supabase에서 문자열 "14:05:00", time 객체, timedelta 등으로 올 수 있음.
    - datetime.time, 문자열("14:05", "14:05:00", "05:05:00+00" 등), timedelta(자정 기준) 처리.
    - UTC(+00/Z)로 오면 KST(UTC+9)로 변환 후 반환.
    """
    if val is None:
        return ""
    # PostgreSQL time → Python datetime.time (strftime 있음)
    if hasattr(val, "strftime"):
        return val.strftime("%H:%M")
    # 일부 드라이버: time을 자정 기준 timedelta로 반환
    if hasattr(val, "total_seconds"):
        try:
            secs = int(val.total_seconds()) % 86400
            if secs < 0:
                secs += 86400
            h, m = secs // 3600, (secs % 3600) // 60
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            pass
    s = str(val).strip()
    is_utc = "Z" in s.upper() or "+00" in s or s.endswith("-00") or s.endswith("+00:00")
    for sep in ("+00", "-00", "Z", "+09", "-09"):
        if sep in s.upper():
            s = s.upper().split(sep)[0].strip()
            if sep in ("+00", "-00", "Z"):
                is_utc = True
            break
    if "T" in s:
        s = s.split("T")[-1].strip()
    # HH:MM 또는 HH:MM:SS[.ffffff] 등에서 숫자만 추출 (time 타입 다양한 형식 대응)
    time_match = re.search(r"(\d{1,2})\s*[:.\s]\s*(\d{1,2})", s)
    if time_match:
        try:
            h, m = int(time_match.group(1)), int(time_match.group(2))
            if is_utc:
                h = (h + 9) % 24
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            pass
    parts = s.replace(".", ":").split(":")
    if len(parts) >= 2:
        try:
            h, m = int(parts[0].strip()), int(parts[1].strip())
            if is_utc:
                h = (h + 9) % 24
            if 0 <= h <= 23 and 0 <= m <= 59:
                return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            pass
    if len(s) >= 5 and s[2] in (":", " ", "."):
        try:
            h, m = int(s[:2]), int(s[3:5])
            if is_utc:
                h = (h + 9) % 24
            return f"{h:02d}:{m:02d}"
        except (ValueError, TypeError):
            return s[:5]
    return s


def _sent_before_today(sent_at, today: str) -> bool:
    """오늘 아직 안 보냈으면 True (remind_sent_at이 null이거나 오늘보다 이전이면 True)."""
    if sent_at is None:
        return True
    if isinstance(sent_at, str):
        date_part = sent_at[:10] if len(sent_at) >= 10 else sent_at
        return date_part < today
    if hasattr(sent_at, "date"):
        return sent_at.date().isoformat() < today
    if hasattr(sent_at, "isoformat"):
        return sent_at.isoformat()[:10] < today
    return True


def _time_in_window(hm: str, now_hm: str, window_minutes: int = 0) -> bool:
    """hm이 now_hm과 일치하거나, window_minutes 이내면 True (시뮬레이션용). window_minutes=0이면 정확히 일치만."""
    if not hm or len(hm) < 5:
        return False
    try:
        h, m = int(hm[:2]), int(hm[3:5])
        nh, nm = int(now_hm[:2]), int(now_hm[3:5])
        now_mins = nh * 60 + nm
        user_mins = h * 60 + m
        if window_minutes <= 0:
            return now_mins == user_mins
        diff = abs(now_mins - user_mins)
        if diff > 12 * 60:  # 자정 넘김
            diff = 24 * 60 - diff
        return diff <= window_minutes
    except (ValueError, TypeError):
        return False


def _filter_by_remind_time(rows: list, now_hm: str, now_hms: str, debug_log: bool = False, time_window_minutes: int = 0) -> list:
    """remind_time이 현재 시각(분 단위)과 일치하는 행만 반환. time_window_minutes>0이면 그 구간 내도 매칭 (시뮬레이션용)."""
    now_normalized = _normalize_remind_time(now_hm if len(now_hm) == 5 else now_hms[:5])
    out = []
    for u in rows:
        raw = u.get("remind_time")
        rt = _normalize_remind_time(raw)
        match = _time_in_window(rt, now_normalized, time_window_minutes) if rt else False
        if debug_log:
            logger.debug(
                "[remind_time] email=%s raw=%r norm=%r now=%r match=%s",
                u.get("email", ""),
                raw,
                rt,
                now_normalized,
                match,
            )
        if match:
            out.append(u)
    return out


def check_and_send_reminders():
    """
    APScheduler에서 매 분 호출.
    DB에서 알림 대상 조회(is_notify=True, remind_time=현재 시각 KST) → 오늘 아직 안 보낸 유저만 Expo Push 발송.
    사용자가 시간을 변경하면 remind_sent_at이 리셋되어 새 시간에 오늘도 발송됨.
    """
    global _remind_sent_at_available
    # 알림 시간은 사용자(KST) 기준이므로, 비교 시에도 KST 사용 (서버가 UTC여도 동작)
    tz_seoul = ZoneInfo("Asia/Seoul")
    now_dt = datetime.now(tz_seoul)
    now = now_dt.strftime("%H:%M")  # 24시간 "14:05"
    now_with_sec = now_dt.strftime("%H:%M:%S")  # DB가 time 타입이면 "14:05:00"
    today = now_dt.date().isoformat()  # YYYY-MM-DD (KST 기준 오늘)

    try:
        simulate = is_notification_simulation()
        # 시뮬레이션: 현재 시간 ±5분 구간 매칭, fcm_token 없어도 대상 포함
        time_window = 5

        def _is_notify_on(val) -> bool:
            if val is None:
                return False
            if isinstance(val, bool):
                return val is True
            if isinstance(val, str):
                return val.strip().lower() in ("true", "1", "yes", "on")
            return bool(val)

        select_cols = "email, fcm_token, remind_time"
        select_cols_with_sent = "email, fcm_token, remind_sent_at, remind_time"
        if simulate:
            base_filter = supabase.table("users").select(select_cols).not_.is_("remind_time", "null")
            response = _supabase_execute_with_connect_retry(base_filter)
            rows_raw = response.data or []
            rows = [u for u in rows_raw if _is_notify_on(u.get("is_notify"))]
            if not rows and rows_raw:
                rows = rows_raw
            use_sent = False
        else:
            if _remind_sent_at_available is False:
                base_filter = supabase.table("users").select(select_cols).eq("is_notify", True)
                response = _supabase_execute_with_connect_retry(base_filter)
                rows = response.data or []
                use_sent = False
            else:
                try:
                    base_filter = supabase.table("users").select(select_cols_with_sent).eq("is_notify", True)
                    response = _supabase_execute_with_connect_retry(base_filter)
                    rows = response.data or []
                    use_sent = True
                except Exception as e:
                    if _remind_sent_at_available is None and _is_remind_sent_at_missing_error(e):
                        _remind_sent_at_available = False
                        logger.warning(
                            "users.remind_sent_at 컬럼 없음 — 이번 회차는 발송 기록 없이 진행."
                        )
                        base_filter = supabase.table("users").select(select_cols).eq("is_notify", True)
                        response = _supabase_execute_with_connect_retry(base_filter)
                        rows = response.data or []
                        use_sent = False
                    else:
                        raise

        if simulate:
            targets = _filter_by_remind_time(
                rows, now, now_with_sec, debug_log=False, time_window_minutes=time_window
            )
        else:
            rows = _filter_by_remind_time(rows, now, now_with_sec, debug_log=False, time_window_minutes=0)
            targets = [u for u in rows if _sent_before_today(u.get("remind_sent_at"), today)] if use_sent else rows

        # 같은 이메일 중복 제거 — 워커 다중 또는 DB 중복 시 한 유저당 한 번만 발송
        seen_emails = set()
        unique_targets = []
        for u in targets:
            email = u.get("email") or ""
            if email not in seen_emails:
                seen_emails.add(email)
                unique_targets.append(u)
        targets = unique_targets

        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")
            if simulate:
                continue
            if not token:
                continue

            ok = send_push_notification(
                token=token,
                title="복습할 시간입니다! 📚",
                body="오늘 공부한 내용을 잊기 전에 확인해보세요.",
            )
            if ok:
                if use_sent and _remind_sent_at_available is not False:
                    try:
                        _supabase_execute_with_connect_retry(
                            supabase.table("users").update({"remind_sent_at": today}).eq("email", email)
                        )
                    except Exception as e:
                        if _is_remind_sent_at_missing_error(e):
                            _remind_sent_at_available = False
                            logger.warning(
                                "users.remind_sent_at 컬럼 없음 — 발송 기록 생략. 컬럼 추가 권장."
                            )
            else:
                logger.error("[알림 스케줄] 발송 실패: %s — Expo 로그 참고", email)

    except Exception as e:
        if is_notification_simulation():
            logger.debug("시뮬레이션 알림 조회/발송 오류 (다음 주기 재시도): %s", e)
            return
        if _remind_sent_at_available is None and _is_remind_sent_at_missing_error(e):
            _remind_sent_at_available = False
            logger.warning(
                "users.remind_sent_at 컬럼 없음 — 발송 기록 없이 재시도. 컬럼 추가 시 리셋 기능 사용 가능."
            )
            check_and_send_reminders()
        else:
            logger.exception("알림 스케줄 태스크 오류")
