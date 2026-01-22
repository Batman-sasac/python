# /, /home, /index

from fastapi import FastAPI, Cookie, Request
from typing import Optional
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app import ocr_app, study_app, user_app, notification_app, reward_app, weekly_app
from app.reward_app import check_attendance_and_reward
import os

import jwt

# 이걸 안 하면 미들웨어가 CSS 파일 요청도 로그인이 안 됐다고 막아버립니다.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


app = FastAPI()
app.include_router(user_app.app)
app.include_router(ocr_app.app)
app.include_router(study_app.app)
app.include_router(notification_app.app)
app.include_router(reward_app.app)
app.include_router(weekly_app.app)

# 앱과 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    exclude_paths = [
        "/", "/auth/login", "/auth/kakao/callback", "auto/kakao/mobile", 
        "/auth/nickName", "/auth/set-nickname", "/static"
    ]
    
    path = request.url.path

    # 1. 예외 경로라면 바로 다음 단계로 진행
    if path in exclude_paths or any(path.startswith(p) for p in exclude_paths):
        return await call_next(request)

    # 2. 헤더에서 토큰 추출
    auth_header = request.headers.get('Authorization') 
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=401, 
            content={"code": "LOGIN_REQUIRED", "detail": "로그인이 필요합니다."}
        )

    token = auth_header.split(" ")[1]

    try:
        # 3. 토큰 검증
        secret_key = os.getenv("JWT_SECRET_KET", "your-secret-key")
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        user_email = payload.get("email")

        # 4. DB 확인
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT nickName FROM users WHERE email = %s", (user_email,))
        user_row = cur.fetchone()

        # 닉네임이 없거나 결과가 없는 경우
        if not user_row or not user_row[0]: # user_row[0]이 nickName
            return JSONResponse(status_code=403, content={"code": "NICKNAME_REQUIRED"})

    except jwt.PyJWTError:
        # 토큰 유효하지 않거나 만료된 경우
        return JSONResponse(status_code=401, content={"code": "INVALID_TOKEN"})
    except Exception as e:
        # 기타 DB 에러 등
        return JSONResponse(status_code=500, content={"detail": str(e)})
    finally:
        # 사용한 커서나 연결이 있다면 여기서 닫아주는 것이 좋습니다.
        cur.close()

    return await call_next(request)



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