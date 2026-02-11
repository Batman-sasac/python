from datetime import datetime
import os

import firebase_admin
from firebase_admin import credentials, messaging

from core.database import supabase


# Firebase 초기화 (한 번만 실행되도록 설정)
def init_firebase():
    """Firebase Admin SDK 초기화 (이미 초기화된 경우 재초기화하지 않음)."""
    if not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_JSON_PATH", "secrets/firebase-adminsdk.json")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase Admin SDK 초기화 완료")


def send_fcm_notification(token: str, title: str, body: str):
    """FCM 푸시 알림 발송."""
    try:
        init_firebase()
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=token,
        )
        response = messaging.send(message)
        return response
    except Exception as e:
        print(f"❌ FCM 전송 실패: {e}")
        return None


def check_and_send_reminders():
    """
    매 분 실행되어야 하는 알림 체크 함수.

    기존에는 Celery Beat + Redis 로 스케줄링되었지만,
    이제는 APScheduler 가 이 함수를 직접 호출하는 방식으로 동작합니다.
    """
    now = datetime.now().strftime("%H:%M")
    try:
        response = (
            supabase.table("users")
            .select("email, fcm_token")
            .eq("is_notify", True)
            .eq("remind_time", now)
            .not_.is_("fcm_token", "null")
            .execute()
        )

        targets = response.data or []

        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")

            if not token:
                continue

            send_fcm_notification(
                token=token,
                title="복습할 시간입니다! 📚",
                body="오늘 공부한 내용을 잊기 전에 확인해보세요.",
            )
            print(f"🔔 알림 발송 완료: {email}")

    except Exception as e:
        print(f"❌ 알림 스케줄 태스크 오류: {e}")
