# /, /home, /index

from fastapi import FastAPI, Request
import uvicorn
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app import ocr_app, study_app, user_app, notification_app, reward_app, weekly_app
from app.firebase import firebase_app
import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import jwt
from database import supabase

app = FastAPI()

# 정적 파일 제공 (필요시)
if os.path.exists("static"):
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(user_app.app)
app.include_router(ocr_app.app)
app.include_router(study_app.app)
app.include_router(notification_app.app)
app.include_router(reward_app.app)
app.include_router(weekly_app.app)
app.include_router(firebase_app.app)

# 앱과 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    import sys
    
    # CORS preflight 요청(OPTIONS)은 인증 없이 통과
    if request.method == "OPTIONS":
        return await call_next(request)
    
    exclude_paths = [
        "/", "/auth/login", "/auth/kakao/callback", "/auth/kakao/mobile", 
        "/auth/naver/callback", "/auth/naver/mobile",
        "/auth/set-nickname",
        "/static", 
    ]
    
    path = request.url.path
    auth_header = request.headers.get('Authorization')
    
    print(f"🔍 요청: {request.method} {path}", flush=True)
    print(f"   Authorization: {auth_header[:50] if auth_header else '없음'}...", flush=True)

    # 1. 예외 경로라면 바로 다음 단계로 진행
    # "/" 단독은 "/"만 매칭하고, 다른 경로는 prefix로 확인
    is_excluded = (path == "/") or any(path.startswith(p) for p in exclude_paths if p != "/")
    
    if is_excluded:
        print(f"   📌 예외 경로 통과", flush=True)
        return await call_next(request)

    # 2. 헤더에서 토큰 추출
    if not auth_header or not auth_header.startswith("Bearer "):
        print(f"❌ Authorization 헤더 없음 또는 잘못됨", flush=True)
        return JSONResponse(
            status_code=401, 
            content={"code": "LOGIN_REQUIRED", "detail": "로그인이 필요합니다."}
        )

    token = auth_header.split(" ")[1]
    print(f"   📌 토큰 추출 완료", flush=True)

    # 3. 토큰 검증
    secret_key = os.getenv("JWT_SECRET_KEY", "your-secret-key")
    print(f"   Secret Key: {'설정됨' if os.getenv('JWT_SECRET_KEY') else '기본값 사용'}", flush=True)
    
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
        print(f"   ✅ 토큰 검증 성공: {payload}", flush=True)
    except jwt.PyJWTError as e:
        print(f"   ❌ 토큰 검증 실패: {e}", flush=True)
        return JSONResponse(status_code=401, content={"code": "INVALID_TOKEN"})
    except Exception as e:
        print(f"   ❌ 예상치 못한 에러: {e}", flush=True)
        return JSONResponse(status_code=500, content={"detail": str(e)})

    # 4. 추출한 이메일을 request.state에 저장
    user_email = payload.get("email")
    print(f"   이메일: {user_email}", flush=True)
    
    if not user_email:
        print(f"   ❌ 토큰에 이메일이 없음", flush=True)
        return JSONResponse(status_code=401, content={"code": "INVALID_TOKEN"})
    
    request.state.user_email = user_email
    print(f"   ✅ request.state.user_email 설정 완료: {user_email}", flush=True)

    # 5. DB 확인은 선택사항으로 변경 (실패해도 진행)
    try:
        db = get_db()
        response = db.table("users").select("nickName").eq("email", user_email).execute()
        user_row = response.data
        print(f"   DB 조회: {user_row}", flush=True)
    except Exception as db_error:
        print(f"   ⚠️ DB 조회 무시: {db_error}", flush=True)

    print(f"   🎯 middleware 통과 - call_next 실행", flush=True)
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