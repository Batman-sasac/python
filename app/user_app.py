import os
from dotenv import load_dotenv
import requests
import psycopg2
from fastapi import APIRouter, Response, Request, Header, Form, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
from dotenv import load_dotenv
from database import supabase
from pydantic import BaseModel
from app.security.security_app import create_jwt_token, get_current_user
import jwt
from datetime import datetime, timedelta, date
from fastapi.responses import JSONResponse
from fastapi import Form



load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])

class KakaoLoginRequest(BaseModel):
    code: str

class NicknameUpdate(BaseModel): # 프론트에 맞춰 Form이 아닌 data로
    nickname: str
    email: Optional[str] = None
    social_id: Optional[str] = None

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
    
    # FormData로 code 받기
    if not code:
        return JSONResponse(status_code=400, content={"error": "code가 필요합니다"})
    
    print(f"[카카오 로그인] code 수신: {code[:20]}...")

    client_id = "5202f1b3b542b79fdf499d766362bef6"
    redirect_uri = "http://127.0.0.1:8000/auth/kakao/mobile"
    
    # 1. 카카오 Access Token 발급
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),
        "redirect_uri": redirect_uri,
        "code": code,
    }

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
    user_email = user_info_res.get("kakao_account", {}).get("email", "")
    token = create_jwt_token(user_email, social_id)

    print(f"JWT token: {token}")

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
                "token": token,
                "email": user_email
            }

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
        print(f"DB 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})


# --- [2. 닉네임 설정 API] ---
@app.post("/set-nickname") 
async def set_nickname_mobile(
    data: NicknameUpdate,
    email: str = Depends(get_current_user)
):
    try:
        nickname = data.nickname
        print(f"토큰 주인 이메일: {email}, 설정하려는 닉네임: {nickname}")

        # 1. social_id 조회 (토큰 생성용)
        user_res = supabase.table("users").select("social_id").eq("email", email).execute()
        social_id = None
        if user_res.data and len(user_res.data) > 0:
            social_id = user_res.data[0].get("social_id") or data.social_id
        if not social_id and data.social_id:
            social_id = data.social_id

        # 2. 닉네임 업데이트 (서버 DB에 저장)
        update_res = supabase.table("users") \
            .update({"nickname": nickname}) \
            .eq("email", email) \
            .execute()

        if not update_res.data:
            return JSONResponse(status_code=404, content={"error": "사용자를 찾을 수 없습니다."})

        # 3. 새 JWT 발급 (프론트엔드가 저장할 수 있도록)
        social_id_str = str(social_id) if social_id else (data.social_id or "unknown")
        token = create_jwt_token(email, social_id_str)

        return {
            "status": "success",
            "token": token,
            "nickname": nickname,
            "email": email,
            "message": "닉네임이 설정되었습니다."
        }
    except Exception as e:
        print(f"닉네임 설정 오류: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- [3. 사용자 학습 통계 (총 학습 횟수, 연속 학습일, 한달 목표)] ---
@app.get("/user/stats")
async def get_user_stats(email: str = Depends(get_current_user)):
    """총 학습 횟수, 총 학습일, 연속 학습일, 한달 목표 반환 (study_logs.completed_at 기준)"""
    try:
        today = date.today()

        # 1. 총 학습 횟수: study_logs 전체 건수
        total_res = supabase.table("study_logs") \
            .select("id", count="exact") \
            .eq("user_email", email) \
            .execute()
        total_learning_count = getattr(total_res, "count", None)
        if total_learning_count is None and total_res.data is not None:
            total_learning_count = len(total_res.data)
        if total_learning_count is None:
            total_learning_count = 0

        # 2. 총 학습일·연속 학습일: study_logs.completed_at 기준 distinct 날짜 계산
        logs_res = supabase.table("study_logs") \
            .select("completed_at") \
            .eq("user_email", email) \
            .execute()
        study_dates = set()
        for row in (logs_res.data or []):
            completed = row.get("completed_at")
            if completed:
                if isinstance(completed, str):
                    study_dates.add(completed[:10])  # YYYY-MM-DD
                else:
                    study_dates.add(str(completed)[:10])
        consecutive_days = 0  # 연속 학습일: 오늘부터 역순으로 연속된 일수
        check = today
        check_str = check.isoformat()
        while check_str in study_dates:
            consecutive_days += 1
            check -= timedelta(days=1)
            check_str = check.isoformat()

        # 3. 한달 목표: users.target_count
        user_res = supabase.table("users") \
            .select("monthly_goal") \
            .eq("email", email) \
            .single() \
            .execute()
        monthly_goal = 0
        if user_res.data and user_res.data.get("monthly_goal") is not None:
            monthly_goal = int(user_res.data["monthly_goal"])

        return {
            "status": "success",
            "data": {
                "total_learning_count": total_learning_count,
                "consecutive_days": consecutive_days,
                "monthly_goal": monthly_goal,
            }
        }
    except Exception as e:
        print(f"사용자 통계 조회 오류: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


    

