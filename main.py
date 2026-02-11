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
from service.notification_service import check_and_send_reminders

load_dotenv()


# 이걸 안 하면 미들웨어가 CSS 파일 요청도 로그인이 안 됐다고 막아버립니다.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


app = FastAPI()
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


# APScheduler: 복습 알림 (DB 기반) 주기 실행
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


@app.on_event("startup")
def start_scheduler():
    """
    서버 시작 시 APScheduler 를 구동하고,
    Celery + Redis 대신 DB 기반 알림 체크 함수를 매 분 실행한다.
    """
    scheduler.add_job(
        check_and_send_reminders,
        "cron",
        minute="*",
        id="check_and_send_reminders",
        replace_existing=True,
    )
    scheduler.start()



@app.get("/")
def root():
    return {"status": "running"}




@app.get("/config")
async def get_config():
    """프론트엔드 OAuth 설정 (환경변수에서 로드)"""
    return {
        "kakao_rest_api_key": os.getenv("KAKAO_REST_API_KEY"),
        "kakao_redirect_uri": os.getenv(
            "KAKAO_REDIRECT_URI",
            (os.getenv("API_BASE_URL") or "http://localhost:8000") + "/auth/kakao/mobile",
        ),
        "naver_client_id": os.getenv("NAVER_CLIENT_ID"),
        "naver_redirect_uri": os.getenv(
            "NAVER_REDIRECT_URI",
            (os.getenv("API_BASE_URL") or "http://127.0.0.1:8000") + "/auth/naver/mobile",
        ),
    }

if __name__ == "__main__":
    port = 8000
    print(f"\n🚀 가동 중:http://192.168.219.110:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)