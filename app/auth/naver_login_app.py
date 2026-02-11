import os
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import requests
from core.database import supabase
from app.security_app import create_jwt_token

app = APIRouter(prefix="/auth", tags=["Auth"])


class NaverMobileLoginRequest(BaseModel):
    code: str
    state: str



# --- [1. 네이버 로그인 콜백 - GET으로 code 받고 HTML 반환] ---
@app.get("/naver/mobile")
async def naver_callback_redirect(code: str, state: str = ""):
    """WebView에서 리다이렉트될 때 호출. HTML 페이지를 반환하여 앱에 code 전달"""
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
            h3 {{ color: #03C75A; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h3>✓ 로그인 성공!</h3>
            <p>잠시 후 자동으로 돌아갑니다...</p>
        </div>
        <script>
            const code = "{code}";
            const state = "{state}";

            if (window.opener) {{
                window.opener.postMessage({{ type: 'OAUTH_CODE', code: code, state: state }}, '*');
                setTimeout(() => window.close(), 500);
            }} else {{
                try {{
                    window.location.href = "bat://oauth-callback?code=" + code + "&state=" + state;
                }} catch(e) {{
                    console.log('Redirect failed:', e);
                }}
            }}
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


# --- [2. 네이버 로그인 처리 - POST로 실제 로그인 및 DB 저장] ---
@app.post("/naver/mobile")
async def naver_callback(code: str = Form(...), state: str = Form("")):
    if not code:
        return JSONResponse(status_code=400, content={"error": "code가 필요합니다"})

    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    redirect_uri = os.getenv("NAVER_REDIRECT_URI", "http://127.0.0.1:8000/auth/naver/mobile")

    if not client_id or not client_secret:
        return JSONResponse(
            status_code=500,
            content={"error": "NAVER_CLIENT_ID, NAVER_CLIENT_SECRET을 .env에 설정해주세요."},
        )

    # 1. 네이버 Access Token 발급
    token_url = "https://nid.naver.com/oauth2.0/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
        "state": state or "naver_mobile",
    }

    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    if not access_token:
        print(f"❌ 네이버 토큰 발급 실패: {token_res}")
        return JSONResponse(
            status_code=400,
            content={"error": "네이버 토큰 발급 실패", "details": token_res},
        )

    # 2. 네이버 사용자 정보 가져오기
    user_info_res = requests.get(
        "https://openapi.naver.com/v1/nid/me",
        headers={"Authorization": f"Bearer {access_token}"},
    ).json()

    response_data = user_info_res.get("response") or {}
    social_id = str(response_data.get("id", ""))
    user_email = response_data.get("email", "")
    if not user_email and response_data.get("id"):
        user_email = f"naver_{social_id}@naver.oauth"

    if not social_id:
        return JSONResponse(
            status_code=400,
            content={"error": "네이버 사용자 정보를 가져올 수 없습니다.", "details": user_info_res},
        )

    token = create_jwt_token(user_email, social_id)

    try:
        # 3. 기존 유저 확인
        user_res = supabase.table("users").select("nickname").eq("social_id", social_id).execute()
        user_data = user_res.data

        if not user_data:
            # [신규 유저] DB 저장
            supabase.table("users").insert({
                "social_id": social_id,
                "email": user_email,
                "nickname": None,
            }).execute()
            print(f"[네이버 로그인] 신규 유저: {user_email}")
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "token": token,
                "email": user_email,
            }

        nickname = user_data[0].get("nickname")
        if not nickname:
            print(f"[네이버 로그인] 닉네임 없는 유저: {user_email}")
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email,
                "token": token,
            }

        print(f"[네이버 로그인] 기존 유저 로그인 성공: {nickname}")
        return {
            "status": "success",
            "token": token,
            "email": user_email,
            "nickname": nickname,
        }

    except Exception as e:
        print(f"DB 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})
