"""
복습 알림: APScheduler로 1분마다 DB 확인 후 FCM 발송.
- Firebase Admin JSON(서비스 계정)으로 푸시 발송.
- 발송 후 users.remind_sent_at 갱신(sent 처리)으로 같은 날 중복 발송 방지.
"""
from datetime import datetime, date
import os

import firebase_admin
from firebase_admin import credentials, messaging

from core.database import supabase


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


def send_fcm_notification(token: str, title: str, body: str) -> bool:
    """FCM 푸시 알림 발송. 성공 시 True."""
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
        print(f"❌ FCM 전송 실패: {e}")
        return False


# remind_sent_at 컬럼 존재 여부 (없으면 매 분 에러 나지 않도록 fallback)
_remind_sent_at_available: bool | None = None


def _is_remind_sent_at_missing_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "remind_sent_at" in msg and ("does not exist" in msg or "42703" in msg)


def _normalize_remind_time(val: str | None) -> str:
    """DB remind_time을 HH:MM 형태로 (14:05:00 → 14:05)."""
    if not val:
        return ""
    s = str(val).strip()
    if len(s) >= 5 and s[2] in (":", " "):
        return s[:5]  # "14:05" or "14:05:00" → "14:05"
    return s


def _filter_by_remind_time(rows: list, now_hm: str, now_hms: str) -> list:
    """remind_time이 현재 시각(분 단위)과 일치하는 행만 반환. DB가 '14:05' 또는 '14:05:00' 저장 시 모두 매칭."""
    out = []
    for u in rows:
        rt = _normalize_remind_time(u.get("remind_time"))
        if rt == now_hm or rt == now_hms[:5] or rt == now_hms:
            out.append(u)
    return out


def check_and_send_reminders():
    """
    APScheduler에서 1분마다 호출.
    DB에서 알림 대상 유저 조회 → FCM 발송 → 발송 후 remind_sent_at 갱신(sent 처리)으로 중복 방지.
    users 테이블에 remind_sent_at 컬럼이 없으면 sent 처리 없이 발송만 함 (에러 없이 동작).
    """
    global _remind_sent_at_available
    now = datetime.now().strftime("%H:%M")  # 24시간 "14:05"
    now_with_sec = datetime.now().strftime("%H:%M:%S")  # DB가 time 타입이면 "14:05:00"
    today = date.today().isoformat()  # YYYY-MM-DD

    try:
        print(f"[알림] 매 분 체크 중 — 현재 시각 {now} (KST)")
        # remind_sent_at 컬럼이 있는지 이미 확인된 경우 그에 맞게 조회
        if _remind_sent_at_available is False:
            response = (
                supabase.table("users")
                .select("email, fcm_token, remind_time")
                .eq("is_notify", True)
                .not_.is_("fcm_token", "null")
                .execute()
            )
            rows = response.data or []
            # remind_time이 DB에서 "14:05" 또는 "14:05:00" 등으로 올 수 있음
            targets = _filter_by_remind_time(rows, now, now_with_sec)
            use_sent = False
        else:
            response = (
                supabase.table("users")
                .select("email, fcm_token, remind_sent_at, remind_time")
                .eq("is_notify", True)
                .not_.is_("fcm_token", "null")
                .execute()
            )
            rows = response.data or []
            rows = _filter_by_remind_time(rows, now, now_with_sec)
            # 오늘 이미 발송한 유저 제외 (중복 방지)
            targets = []
            for u in rows:
                sent_at = u.get("remind_sent_at")
                if sent_at is None:
                    targets.append(u)
                elif isinstance(sent_at, str) and sent_at < today:
                    targets.append(u)
                elif hasattr(sent_at, "isoformat") and sent_at.isoformat() < today:
                    targets.append(u)
            use_sent = True

        if not targets:
            print(f"[알림] 발송 대상 0명 (is_notify=True, remind_time={now}, fcm_token 있는 유저 확인)")
        else:
            print(f"[알림] 발송 대상 {len(targets)}명")

        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")
            if not token:
                continue

            ok = send_fcm_notification(
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
        if _remind_sent_at_available is None and _is_remind_sent_at_missing_error(e):
            _remind_sent_at_available = False
            print("⚠️ users.remind_sent_at 컬럼 없음 — sent 없이 재시도. 컬럼 추가 시 migrations/add_remind_sent_at.sql 참고.")
            check_and_send_reminders()  # 한 번만 fallback으로 재실행
        else:
            print(f"❌ 알림 스케줄 태스크 오류: {e}")
