from fastapi import FastAPI, Cookie, Request
from typing import Optional
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app import ocr_app, quiz_app, user_app, notification_app
import os

# 이걸 안 하면 미들웨어가 CSS 파일 요청도 로그인이 안 됐다고 막아버립니다.
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


app = FastAPI()
app.include_router(user_app.app)
app.include_router(ocr_app.app)
app.include_router(quiz_app.app)
app.include_router(notification_app.app)

# 브라우저 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # 1. 예외 경로 설정 (로그인 없이도 접근 가능해야 하는 곳)
    exclude_paths = [
    "/", "/auth/login", "/auth/kakao/callback", 
    "/auth/nickName", "/auth/set-nickname", "/static"
]
    
    # 현재 요청 경로 확인
    path = request.url.path

    # 2. 예외 경로가 아니고, 쿠키에 user_email이 없는 경우
    if path not in exclude_paths and not any(path.startswith(p) for p in exclude_paths):
        user_email = request.cookies.get("user_email")
        
        if not user_email:
            # 브라우저 페이지 요청(HTML)인 경우 리다이렉트
            if "text/html" in request.headers.get("accept", ""):
                return RedirectResponse(url="/auth/login")
            # API 요청(JSON)인 경우 401 에러 반환 (프론트엔드 fetch 대응)
            else:
                return JSONResponse(status_code=401, content={"detail": "Not authenticated"})

    # 3. 로그인이 되어있거나 예외 경로라면 정상 진행
    response = await call_next(request)
    return response

@app.get("/", response_class=HTMLResponse)
async def login_page(session_user: Optional[str] = Cookie(None)):
    # 이미 로그인된 사용자라면 인덱스로 바로 이동
        
    with open("templates/login.html", "r", encoding="utf-8") as f:
        content = f.read()
    
    # .env의 REST API 키를 HTML의 {{KAKAO_REST_API_KEY}} 부분에 주입
    rest_key = os.getenv("KAKAO_REST_API_KEY")
    return content.replace("{{KAKAO_REST_API_KEY}}", str(rest_key))

@app.get("/index", response_class=HTMLResponse)
async def index_page(): 
    
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    print(f"\n🚀 서버 가동 중: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)