from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from core.database import supabase

import firebase_admin
from firebase_admin import credentials, messaging
import os

scheduler = BackgroundScheduler()

# Firebase 초기화 (한 번만 실행되도록 설정)
def init_firebase():
    if not firebase_admin._apps:
        # JSON 키 파일 경로 
        cred_path = os.getenv("FIREBASE_JSON_PATH", "secrets/firebase-adminsdk.json")
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print("🔥 Firebase Admin SDK 초기화 완료")


def send_fcm_notification(token: str, title: str, body: str):
    try:
        init_firebase() # 실행 전 초기화 확인
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