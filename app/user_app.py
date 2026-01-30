import os
import requests
import psycopg2
from fastapi import APIRouter, Response, Request, Header
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

# --- [1. 카카오 로그인 콜백] ---
@app.get("/kakao/mobile")
async def kakao_callback(code: str):
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

        if user_row is None:
            # [신규 유저] DB 저장 (닉네임은 NULL로 시작)
            supabase.table("users").insert({
                "social_id": social_id, 
                "email": user_email, 
                "nickname": None
            }).execute()
            
            # 신규 유저는 닉네임 설정 페이지로 유도 (클라이언트에서 처리할 status 반환)
            return {
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email
            }

        # [기존 유저] 닉네임이 이미 있다면 바로 토큰 발급
        nickname = user_data[0].get("nickname")
        if not nickname: # 가입은 했으나 닉네임이 없는 경우 처리
            return HTMLResponse(content = )
            
        token = create_jwt_token(user_email, social_id)
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

    conn = get_db()
    cur = conn.cursor()
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




    

