# /, /home, /index

import logging
import os
from typing import Optional

from dotenv import load_dotenv

load_dotenv()
from app.logging_config import configure_logging

configure_logging()

import jwt
import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
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
from app.auth import kakao_login_app, naver_login_app, apple_login_app
from app.hint import hint_app
from app.firebase_app import app as firebase_app
from app.reward_app import check_attendance_and_reward
from service.notification_service import check_and_send_reminders, is_notification_simulation

logger = logging.getLogger(__name__)

# OCR 2열 보정: service/clova_ocr_service._fields_to_page_text 가 OCR_TWO_COLUMN_LAYOUT 를 읽음 (추가 import 불필요)
if os.getenv("OCR_TWO_COLUMN_LAYOUT", "").lower() in ("1", "true", "yes"):
    logger.info(
        "OCR_TWO_COLUMN_LAYOUT 활성화 — 2열 단어장일 때 original_text 를 왼쪽|오른쪽 형태로 합침"
    )

app = FastAPI()

# 이걸 안 하면 미들웨어가 CSS 파일 요청도 로그인이 안 됐다고 막아버립니다.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(user_app.app)
app.include_router(naver_login_app.app)
app.include_router(kakao_login_app.app)
app.include_router(apple_login_app.app)
app.include_router(ocr_app.app)
app.include_router(study_app.app)
app.include_router(hint_app.app)
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


# APScheduler: 매 분 DB 확인 후 복습 알림 발송 (지정한 시간이 5분 단위가 아니어도 맞춤)
scheduler = BackgroundScheduler(timezone="Asia/Seoul")


@app.on_event("startup")
def start_scheduler():
    """매 분 DB에서 알림 대상 조회 → remind_time과 현재 시각(KST) 일치 시 Expo Push 발송."""
    scheduler.add_job(
        check_and_send_reminders,
        "cron",
        minute="*/5",
        id="check_and_send_reminders",
        replace_existing=True,
    )
    scheduler.start()
    sim_val = os.getenv("NOTIFICATION_SIMULATE", "")
    mode = "시뮬레이션(DB 갱신 없음)" if is_notification_simulation() else "실제 발송"
    logger.info(
        "알림 스케줄러 시작 (5분마다) mode=%s NOTIFICATION_SIMULATE=%r",
        mode,
        sim_val,
    )
   



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
    logger.info("로컬 개발 서버 시작 port=%s", port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=os.getenv("UVICORN_LOG_LEVEL", "info"),
        access_log=False,
    )