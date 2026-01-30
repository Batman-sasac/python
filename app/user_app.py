import os
import requests
import psycopg2
from fastapi import APIRouter, Response, Request, Header, Form
from fastapi.responses import RedirectResponse
from typing import Optional
from dotenv import load_dotenv
from database import supabase
from pydantic import BaseModel
from app.security_app import create_jwt_token
import jwt
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse


load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])

class UserData(BaseModel):
    nickname: str # 소문자 nickname으로 통일

# --- [1. 카카오 로그인 콜백 - GET으로 code 받고 HTML 반환] ---
@app.get("/kakao/mobile")
async def kakao_callback_redirect(code: str):
    """WebView에서 리다이렉트될 때 호출. HTML 페이지를 반환하여 앱에 code 전달"""
    from fastapi.responses import HTMLResponse
    
    # 웹과 모바일 모두 지원하는 HTML
    html_content = f"""
    <html>
    <head>
        <title>로그인 중...</title>
        <meta charset="utf-8">
        <style>
            body {{ 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            }}
            .container {{ text-align: center; }}
            h3 {{ color: #5E82FF; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h3>✓ 로그인 성공!</h3>
            <p>잠시 후 자동으로 돌아갑니다...</p>
        </div>
        <script>
            const code = "{code}";
            
            // 웹 환경: postMessage로 부모 창에 code 전달
            if (window.opener) {{
                window.opener.postMessage({{ type: 'OAUTH_CODE', code: code }}, '*');
                setTimeout(() => window.close(), 500);
            }}
            // 모바일 WebView: custom scheme으로 리다이렉트
            else {{
                try {{
                    window.location.href = "bat://oauth-callback?code=" + code;
                }} catch(e) {{
                    console.log('Redirect failed:', e);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# --- [1-2. 카카오 로그인 처리 - POST로 실제 로그인] ---
@app.post("/kakao/mobile")
async def kakao_callback(code: str = Form(...)):
    from fastapi import Form
    
    # FormData로 code 받기
    if not code:
        return JSONResponse(status_code=400, content={"error": "code가 필요합니다"})
    
    print(f"[카카오 로그인] code 수신: {code[:20]}...")
    
    # 1. 카카오 Access Token 발급
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("KAKAO_REST_API_KEY"),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),
        "redirect_uri": "http://127.0.0.1:8000/auth/kakao/mobile",
        "code": code,
    }
    
    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    if not access_token:
        return JSONResponse(status_code=400, content={"error": "카카오 토큰 발급 실패", "details": token_res})

    # 2. 카카오 사용자 정보 가져오기
    user_info_res = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    social_id = str(user_info_res.get("id"))
    user_email = user_info_res.get("kakao_account", {}).get("email", "")

    try:
        # 3. 기존 유저 확인
        user_res = supabase.table("users").select("nickname").eq("social_id", social_id).execute()
        user_data = user_res.data

        if not user_data:
            # [신규 유저] DB 저장 (닉네임은 NULL로 시작)
            supabase.table("users").insert({
                "social_id": social_id, 
                "email": user_email, 
                "nickname": None
            }).execute()
            
            print(f"[카카오 로그인] 신규 유저: {user_email}")
            # 신규 유저는 닉네임 설정 페이지로 유도 (클라이언트에서 처리할 status 반환)
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email
            }

        # [기존 유저] 닉네임이 이미 있다면 바로 토큰 발급
        nickname = user_data[0].get("nickname")
        if not nickname: # 가입은 했으나 닉네임이 없는 경우 처리
            print(f"[카카오 로그인] 닉네임 없는 유저: {user_email}")
            return {"status": "NICKNAME_REQUIRED", "social_id": social_id, "email": user_email}
            
        token = create_jwt_token(user_email, social_id)
        print(f"[카카오 로그인] 기존 유저 로그인 성공: {nickname}")
        return {
            "status": "success",
            "token": token,
            "email": user_email,
            "nickname": nickname
        }

    except Exception as e:
        print(f"DB 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


# --- [2. 닉네임 설정 API] ---
@app.post("/set-nickname")
async def set_nickname(request: Request, data: UserData):
    # 미들웨어에서 검증된 이메일 사용
    email = request.state.user_email 
    new_nickname = data.nickname

    try:
        # 1. 닉네임 중복 체크 (다른 사람이 이미 쓰고 있는지)
        check_res = supabase.table("users").select("email").eq("nickname", new_nickname).execute()
        
        if check_res.data:
            return JSONResponse(
                status_code=400, 
                content={"status": "duplicated", "message": "이미 사용 중인 닉네임입니다."}
            )

        # 2. 닉네임 업데이트 (RLS가 걸려있다면 본인 확인 절차가 DB에서 한 번 더 수행됨)
        supabase.table("users").update({"nickname": new_nickname}).eq("email", email).execute()

        return {
            "status": "success",
            "nickname": new_nickname,
            "email": email
        }
    except Exception as e:
        print(f"❌ 닉네임 저장 에러: {e}")
        return JSONResponse(status_code=500, content={"detail": "서버 오류"})




    

