# /, /home, /index

import os
from typing import Optional

import jwt
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import (
    notification_app,
    ocr_app,
    reports_app,
    reward_app,
    study_app,
    user_app,
    weekly_app,
)
from app.auth import kakao_login_app, naver_login_app
from app.firebase_app import app as firebase_app
from app.reward_app import check_attendance_and_reward
from service.notification_service import check_and_send_reminders, is_notification_simulation

load_dotenv()

app = FastAPI()

# 이걸 안 하면 미들웨어가 CSS 파일 요청도 로그인이 안 됐다고 막아버립니다.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(user_app.app)
app.include_router(naver_login_app.app)
app.include_router(kakao_login_app.app)
app.include_router(ocr_app.app)
app.include_router(study_app.app)
app.include_router(notification_app.app)
app.include_router(reward_app.app)
app.include_router(weekly_app.app)
app.include_router(firebase_app)
app.include_router(reports_app.app)

# 앱과 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True
)


# APScheduler: 5분마다 DB 확인 후 FCM 복습 알림 발송 (발송 후 sent 처리로 중복 방지)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


@app.on_event("startup")
def start_scheduler():
    """5분마다 DB에서 알림 대상 조회 → Firebase Admin JSON으로 FCM 발송 → sent 처리."""
    scheduler.add_job(
        check_and_send_reminders,
        "cron",
        minute="*/5",
        id="check_and_send_reminders",
        replace_existing=True,
    )
    scheduler.start()
    mode = "🧪 시뮬레이션 (FCM/DB 갱신 없음)" if is_notification_simulation() else "실제 발송"
    print(f"⏰ 알림 스케줄러 시작 — 5분마다 복습 알림 체크 ({mode})")
   



@app.get("/")
def root():
    return {"status": "running"}




@app.get("/config")
async def get_config():
    """프론트엔드 OAuth 설정 (환경변수에서 로드)"""

    base_url = os.getenv("API_BASE_URL", "http://54.206.80.239:8000")

    return {
        "kakao_rest_api_key": os.getenv("KAKAO_REST_API_KEY"),
        "kakao_redirect_uri": os.getenv("KAKAO_REDIRECT_URI", f"{base_url}/auth/kakao/mobile"),
        "naver_client_id": os.getenv("NAVER_CLIENT_ID"),
        "naver_redirect_uri": os.getenv("NAVER_REDIRECT_URI", f"{base_url}/auth/naver/mobile"),
    }

if __name__ == "__main__":
    port = 8000
    print(f"\n🚀 서버 가동 중 - Port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)