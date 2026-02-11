from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse
from core.database import supabase
import os
import requests
from app.security_app import create_jwt_token
from pydantic import BaseModel

app = APIRouter(prefix="/auth", tags=["Auth"])

# .env 로드 (security_app import 시 로드되지만, 독립 실행 시 대비)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

class KakaoLoginRequest(BaseModel):
    code: str



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
    import traceback
    try:
        return await _kakao_callback_impl(code)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[카카오 로그인] 예외 발생: {e}")
        print(tb)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(e)},
        )


async def _kakao_callback_impl(code: str):
    if not code:
        return JSONResponse(status_code=400, content={"error": "code가 필요합니다"})
    
    print(f"[카카오 로그인] code 수신: {code[:20]}...")

    client_id = os.getenv("KAKAO_REST_API_KEY")
    redirect_uri = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8000/auth/kakao/mobile")
    client_secret = os.getenv("KAKAO_CLIENT_SECRET")

    if not client_id:
        return JSONResponse(
            status_code=500,
            content={"error": "KAKAO_REST_API_KEY를 .env에 설정해주세요."},
        )

    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "code": code,
    }
    if client_secret:
        token_data["client_secret"] = client_secret

    print(f"[STEP 2] 카카오 토큰 요청 데이터 확인:")
    print(f" - URL: {token_url}")
    print(f" - Client ID: {client_id}")
    print(f" - Redirect URI: {redirect_uri}")
    print(f"{'='*30}")
    
    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    print(f"access_token: {access_token}" )

    if not access_token:
    # 이 부분을 추가해서 카카오가 보내는 진짜 에러 메시지를 확인하세요!
        print(f"❌ 카카오 토큰 발급 실패 상세 로그: {token_res}") 
        return JSONResponse(status_code=400, content={"error": "카카오 토큰 발급 실패", "details": token_res})

    # 2. 카카오 사용자 정보 가져오기
    user_info_res = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    social_id = str(user_info_res.get("id"))
    user_email = user_info_res.get("kakao_account", {}).get("email", "") or ""
    if not user_email:
        user_email = f"kakao_{social_id}@kakao.oauth"
    token = create_jwt_token(user_email, social_id)

    print(f"JWT token: {token}")

    try:
        # 3. 기존 유저 확인
        user_res = supabase.table("users").select("nickname").eq("social_id", social_id).execute()
        user_data = user_res.data

        if not user_data:
            try:
                # [신규 유저] DB 저장 (닉네임은 NULL로 시작)
                supabase.table("users").insert({
                    "social_id": social_id,
                    "email": user_email,
                    "nickname": None
                }).execute()
                print(f"[카카오 로그인] 신규 유저: {user_email}")
                return {
                    "status": "NICKNAME_REQUIRED",
                    "social_id": social_id,
                    "token": token,
                    "email": user_email
                }
            except Exception as insert_err:
                err_str = str(insert_err)
                # 이메일 중복: 기존 계정에 카카오 social_id 연결
                if "23505" in err_str or "duplicate key" in err_str.lower() or "users_email_key" in err_str:
                    print(f"[카카오 로그인] 이메일 중복 - 기존 계정에 연동: {user_email}")
                    exist_res = supabase.table("users").select("nickname, social_id").eq("email", user_email).execute()
                    if exist_res.data:
                        row = exist_res.data[0]
                        supabase.table("users").update({"social_id": social_id}).eq("email", user_email).execute()
                        nickname = row.get("nickname")
                        if not nickname:
                            return {"status": "NICKNAME_REQUIRED", "social_id": social_id, "email": user_email, "token": token}
                        return {"status": "success", "token": token, "email": user_email, "nickname": nickname}
                raise

        # [기존 유저] 닉네임이 이미 있다면 바로 토큰 발급
        nickname = user_data[0].get("nickname")
        if not nickname: # 가입은 했으나 닉네임이 없는 경우 처리
            print(f"[카카오 로그인] 닉네임 없는 유저: {user_email}")
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email,
                "token": token
                }
            
        print(f"[카카오 로그인] 기존 유저 로그인 성공: {nickname}")
        return {
            "status": "success",
            "token": token,
            "email": user_email,
            "nickname": nickname
        }

    except Exception as e:
        raise

