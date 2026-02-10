# /, /home, /index

from fastapi import FastAPI, Request
from typing import Optional
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app import reports_app, ocr_app, study_app, user_app, notification_app, reward_app, weekly_app
from app.auth import naver_login_app, kakao_login_app
from app.firebase_app import app as firebase_app
from app.reward_app import check_attendance_and_reward


import os

import jwt


from service.notification_service import send_fcm_notification

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





@app.get("/config")
async def get_config():
    # 설정 정보 반환
    return {
        "kakao_rest_api_key": os.getenv("KAKAO_REST_API_KEY"),
        "naver_cilent_id": os.getenv("NAVER_CLIENT_ID")
    }

"""

@app.get("/index", response_class=HTMLResponse)
async def index_page(user_email: str = Cookie(None)):
    # 출석 체크 리워드 

    is_new_reward = False
    total_points = 0

    if user_email:
        # 여기서 두 개의 값을 받습니다.
        is_new_reward, total_points = await check_attendance_and_reward(user_email)

    
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

    if is_new_reward:
        # 간단한 자바스크립트 삽입 예시
        content = content.replace("</body>", f"<script>alert('오늘의 출석 보상 1P가 지급되었습니다! (총 {total_points}P)');</script></body>")
    return content

@app.get("/home", response_class=HTMLResponse)
async def index_page(): 

    
    
    with open("templates/home.html", "r", encoding="utf-8") as f:
        return f.read()

        """

if __name__ == "__main__":
    port = 8000
    print(f"\n🚀 가동 중:http://192.168.219.110:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)