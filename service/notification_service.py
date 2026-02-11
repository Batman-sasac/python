from datetime import datetime
from core.database import supabase
import firebase_admin
from firebase_admin import credentials, messaging
import os

from celery_app import celery


# Firebase 초기화 (한 번만 실행되도록 설정)
def init_firebase():
    if not firebase_admin._apps:
        cred_path = os.getenv("FIREBASE_JSON_PATH", "secrets/firebase-adminsdk.json")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase Admin SDK 초기화 완료")


def send_fcm_notification(token: str, title: str, body: str):
    """FCM 푸시 알림 발송"""
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


@celery.task
def check_and_send_reminders():
    """매 분 Celery Beat에 의해 실행 - DB remind_time 일치 유저에게 FCM 발송"""
    now = datetime.now().strftime("%H:%M")
    try:
        response = supabase.table("users") \
            .select("email, fcm_token") \
            .eq("is_notify", True) \
            .eq("remind_time", now) \
            .not_.is_("fcm_token", "null") \
            .execute()

        targets = response.data

        for user in targets:
            email = user.get("email")
            token = user.get("fcm_token")

            send_fcm_notification(
                token=token,
                title="복습할 시간입니다! 📚",
                body="오늘 공부한 내용을 잊기 전에 확인해보세요."
            )
            print(f"🔔 알림 발송 완료: {email}")

    except Exception as e:
        print(f"❌ 알림 스케줄 태스크 오류: {e}")
