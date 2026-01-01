from fastapi import FastAPI, Cookie
from typing import Optional
import uvicorn
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from app import ocr_app, quiz_app, user_app
import os

app = FastAPI()
app.include_router(user_app.app)

# 브라우저 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", response_class=HTMLResponse)
async def login_page(session_user: Optional[str] = Cookie(None)):
    # 이미 로그인된 사용자라면 인덱스로 바로 이동
    if session_user:
        return RedirectResponse(url="/index")
        
    with open("templates/login.html", "r", encoding="utf-8") as f:
        content = f.read()
    
    # .env의 REST API 키를 HTML의 {{KAKAO_REST_API_KEY}} 부분에 주입
    rest_key = os.getenv("KAKAO_REST_API_KEY")
    return content.replace("{{KAKAO_REST_API_KEY}}", str(rest_key))

@app.get("/index", response_class=HTMLResponse)
async def index_page(user_email: Optional[str] = Cookie(None)): # 변수명 확인!
    print(f"현재 브라우저에서 넘어온 쿠키 값: {user_email}") # 서버 터미널에 출력됨
    
    if not user_email:
        print("쿠키가 없어서 로그인 페이지로 튕깁니다.")
        return RedirectResponse(url="/")
    
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    print(f"\n🚀 서버 가동 중: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)