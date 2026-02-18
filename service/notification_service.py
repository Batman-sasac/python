"""
복습 알림: APScheduler로 5분마다 DB 확인 후 FCM/Expo 푸시 발송.
- Firebase Admin JSON(서비스 계정)으로 FCM 발송 (Android).
- iOS/iPad: getDevicePushTokenAsync가 APNs 토큰을 반환하므로 Firebase와 호환되지 않음.
  → getExpoPushTokenAsync 사용 시 ExponentPushToken → Expo Push API로 발송.
- 발송 후 users.remind_sent_at 갱신(sent 처리)으로 같은 날 중복 발송 방지.
- DB remind_time 컬럼이 PostgreSQL time 타입이어도 정규화 후 비교.
"""
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import os

import firebase_admin
from firebase_admin import credentials, messaging
import requests

from core.database import supabase

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


def is_notification_simulation() -> bool:
    """FCM/DB 없이 알림 로직·스케줄러만 테스트할 때 True. env: NOTIFICATION_SIMULATE=1 또는 true"""
    v = (os.getenv("NOTIFICATION_SIMULATE") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


# Firebase Admin JSON 경로 (.env: FIREBASE_CREDENTIALS 또는 FIREBASE_JSON_PATH)
def _get_firebase_cred_path() -> str:
    return (
        os.getenv("FIREBASE_CREDENTIALS")
        or os.getenv("FIREBASE_JSON_PATH")
        or "secrets/firebase-adminsdk.json"
    )


def init_firebase():
    """Firebase Admin SDK 초기화 (FCM 서버 키가 포함된 서비스 계정 JSON 사용)."""
    if not firebase_admin._apps:
        cred_path = _get_firebase_cred_path()
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase Admin SDK 초기화 완료 (서비스 계정 JSON)")


def _is_expo_push_token(token: str) -> bool:
    """ExponentPushToken 형식이면 True. iOS/iPad용 Expo 푸시에 사용."""
    return bool(token and token.strip().startswith("ExponentPushToken["))


def send_expo_notification(token: str, title: str, body: str) -> bool:
    """
    Expo Push API로 푸시 발송. iOS/iPad에서 ExponentPushToken 사용 시 필요.
    Firebase는 APNs 토큰을 받을 수 없어 iOS 기기에는 Expo API를 사용해야 함.
    """
    if is_notification_simulation():
        print(f"🧪 [시뮬레이션] Expo 푸시 발송 스킵 — token={token[:30]}... title={title!r}")
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
        data = resp.json()
        if data.get("data"):
            ticket = data["data"][0] if isinstance(data["data"], list) else data["data"]
            if ticket.get("status") == "error":
                msg = ticket.get("message", "unknown")
                print(f"❌ Expo 푸시 실패 (토큰): {msg}")
                return False
        return True
    except requests.RequestException as e:
        print(f"❌ Expo 푸시 전송 실패: {e}")
        return False
    except Exception as e:
        print(f"❌ Expo 푸시 예외: {e}")
        return False


def _send_fcm_notification(token: str, title: str, body: str) -> bool:
    """FCM 푸시 알림 발송 (Android FCM 토큰 전용). 성공 시 True."""
    if is_notification_simulation():
        print(f"🧪 [시뮬레이션] FCM 발송 스킵 — token={token[:20]}... title={title!r}")
        return True
    try:
        init_firebase()
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=token,
        )
        messaging.send(message)
        return True
    except Exception as e:
        err_msg = str(e).lower()
        # iOS APNs 토큰을 FCM에 보내면 "invalid" 또는 "registration token" 오류 발생
        if "invalid" in err_msg or "registration" in err_msg or "not a valid fcm" in err_msg:
            print(
                f"❌ FCM 전송 실패 (토큰 형식 불일치): {e} "
                f"→ iOS/iPad는 getExpoPushTokenAsync로 ExponentPushToken을 사용하세요."
            )
        else:
            print(f"❌ FCM 전송 실패: {e}")
        return False


def send_push_notification(token: str, title: str, body: str) -> bool:
    """
    토큰 형식에 따라 적절한 푸시 채널로 발송.
    - ExponentPushToken[...] → Expo Push API (iOS/iPad + Expo 토큰 사용 시)
    - 그 외 → Firebase FCM (Android)
    """
    if not token or not token.strip():
        return False
    token = token.strip()
    if _is_expo_push_token(token):
        return send_expo_notification(token, title, body)
    return _send_fcm_notification(token, title, body)


# remind_sent_at 컬럼 존재 여부 (없으면 매 분 에러 나지 않도록 fallback)
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
    """오늘 이전에 발송했는지 (remind_sent_at이 오늘 날짜보다 이전이면 True)."""
    if sent_at is None:
        return True
    if isinstance(sent_at, str):
        date_part = sent_at[:10] if len(sent_at) >= 10 else sent_at
        return date_part < today
    if hasattr(sent_at, "date"):
        return sent_at.date().isoformat() < today
    if hasattr(sent_at, "isoformat"):
        return sent_at.isoformat()[:10] < today
    return False


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
            print(f"    [remind_time] email={u.get('email','')} raw={raw!r} type={type(raw).__name__} → norm={rt!r} now={now_normalized!r} match={match}")
        if match:
            out.append(u)
    return out


def check_and_send_reminders():
    """
    APScheduler에서 5분마다 호출.
    DB에서 알림 대상 유저 조회 → FCM 발송 → 발송 후 remind_sent_at 갱신(sent 처리)으로 중복 방지.
    users 테이블에 remind_sent_at 컬럼이 없으면 sent 처리 없이 발송만 함 (에러 없이 동작).
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
        time_window = 5 if simulate else 0

        print(f"[알림] ========== 스케줄 실행 (KST {now} / today={today}) ==========")
        if simulate:
            print(f"[알림] 🧪 시뮬레이션 모드 — 현재 시각 {now} (KST), {time_window}분 구간 매칭 (FCM/DB 갱신 없음)")
        else:
            print(f"[알림] 매 분 체크 중 — 현재 시각 {now} (KST)")

        # [진단] 필터 없이 users 일부 조회 (0명일 때 원인 파악용)
        diag_rows = []
        diag_ok = False
        try:
            diag = supabase.table("users").select("email, is_notify, remind_time").limit(30).execute()
            diag_rows = diag.data or []
            diag_ok = True
            print(f"[알림] [진단] 필터 없이 users 조회: {len(diag_rows)}건")
            for i, row in enumerate(diag_rows[:10], 1):
                inot = row.get("is_notify")
                rt = row.get("remind_time")
                print(f"[알림] [진단]   #{i} is_notify={inot!r} (type={type(inot).__name__}) remind_time={rt!r} (type={type(rt).__name__ if rt is not None else 'None'})")
            if len(diag_rows) > 10:
                print(f"[알림] [진단]   ... 외 {len(diag_rows) - 10}건")
        except Exception as e:
            print(f"[알림] [진단] 조회 실패: {e}")
        if diag_ok and not diag_rows:
            print(f"[알림] [진단] users 테이블 0건 → RLS/권한 또는 테이블명 확인. 서비스 역할 키(SUPABASE_SERVICE_ROLE_KEY) 필요할 수 있음.")

        def _is_notify_on(val) -> bool:
            if val is None:
                return False
            if isinstance(val, bool):
                return val is True
            if isinstance(val, str):
                return val.strip().lower() in ("true", "1", "yes", "on")
            return bool(val)

        select_cols = "email, fcm_token, remind_time"
        if simulate:
            # 시뮬레이션: 조건 완화. remind_time만 not null로 조회 후 Python에서 is_notify 필터
            base_filter = supabase.table("users").select(select_cols).not_.is_("remind_time", "null")
            response = base_filter.execute()
            rows_raw = response.data or []
            rows = [u for u in rows_raw if _is_notify_on(u.get("is_notify"))]
            if not rows and rows_raw:
                print(f"[알림] is_notify=True 필터 후 0명 (전체 {len(rows_raw)}명) → is_notify 무시하고 remind_time만 사용")
                rows = rows_raw
            use_sent = False
        else:
            # 토큰 없어도 대상 조회 (발송 시에만 token 없으면 스킵)
            base_filter = supabase.table("users").select(
                select_cols if _remind_sent_at_available is False
                else "email, fcm_token, remind_sent_at, remind_time"
            ).eq("is_notify", True)
            response = base_filter.execute()
            rows = response.data or []
            use_sent = _remind_sent_at_available is not False

        if not rows:
            print(f"[알림] DB 조회 0명 (remind_time 있는 유저 없음)" if simulate else f"[알림] DB 조회 0명 (is_notify=True 유저 없음)")
        else:
            sample = rows[0].get("remind_time")
            print(f"[알림] DB 조회 {len(rows)}명 | 비교 기준 now={now} (KST), time_window={time_window}분")
            print(f"[알림] remind_time 샘플(1번째): raw={sample!r} type={type(sample).__name__} → norm={_normalize_remind_time(sample)!r}")
            # 전체 행의 remind_time 로그 (몇 명 없으면 전부 출력)
            for i, u in enumerate(rows[:20], 1):
                r = u.get("remind_time")
                n = _normalize_remind_time(r)
                print(f"[알림]   #{i} email={u.get('email','')} remind_time raw={r!r} → norm={n!r}")
            if len(rows) > 20:
                print(f"[알림]   ... 외 {len(rows) - 20}명")

        print(f"[알림] 시간 필터 적용 중 (now={now}, 구간={time_window}분)...")
        if simulate:
            targets = _filter_by_remind_time(rows, now, now_with_sec, debug_log=True, time_window_minutes=time_window)
        else:
            rows = _filter_by_remind_time(rows, now, now_with_sec, debug_log=True, time_window_minutes=0)
            targets = [u for u in rows if _sent_before_today(u.get("remind_sent_at"), today)] if use_sent else rows

        # 오늘 아직 알림 안 받은 사용자 조회 결과 로그 (디버그용)
        print(f"[알림] ---------- 결과: {len(targets)}명 알림 대상 ----------")
        for u in targets:
            email = u.get("email") or "-"
            token_val = u.get("fcm_token") or ""
            token_display = (f"{token_val[:12]}...{token_val[-8:]}" if len(token_val) > 24 else token_val) or "(없음)"
            print(f"  - 대상: {email}, FCM 토큰: {token_display}")

        if not targets:
            print(f"[알림] 발송 대상 0명 (remind_time={now} 매칭 없음)" + ("" if simulate else " 또는 fcm_token 없음"))
        else:
            print(f"[알림] 발송 대상 {len(targets)}명 → 발송 처리 시작")

        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")
            if simulate:
                if token:
                    print(f"🧪 [시뮬레이션] 알림 발송 (실제 미발송): {email}")
                else:
                    print(f"🧪 [시뮬레이션] 알림 대상이지만 FCM 토큰 없음 — 스킵: {email}")
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
                        supabase.table("users").update({"remind_sent_at": today}).eq("email", email).execute()
                        print(f"🔔 알림 발송 및 sent 처리 완료: {email}")
                    except Exception as e:
                        if _is_remind_sent_at_missing_error(e):
                            _remind_sent_at_available = False
                            print("⚠️ users.remind_sent_at 컬럼 없음 — sent 처리 생략. 중복 방지를 위해 migrations/add_remind_sent_at.sql 실행 권장.")
                        print(f"🔔 알림 발송 완료: {email}")
                else:
                    print(f"🔔 알림 발송 완료: {email}")

    except Exception as e:
        if is_notification_simulation():
            print(f"🧪 [시뮬레이션] 알림 조회/발송 로직 오류 (무시하고 다음 주기에 재시도): {e}")
            return
        if _remind_sent_at_available is None and _is_remind_sent_at_missing_error(e):
            _remind_sent_at_available = False
            print("⚠️ users.remind_sent_at 컬럼 없음 — sent 없이 재시도. 컬럼 추가 시 migrations/add_remind_sent_at.sql 참고.")
            check_and_send_reminders()  # 한 번만 fallback으로 재실행
        else:
            print(f"❌ 알림 스케줄 태스크 오류: {e}")
