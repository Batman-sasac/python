import os
import requests
import psycopg2
from fastapi import APIRouter, Response, Request, header
from fastapi.responses import RedirectResponse
from typing import Optional
from dotenv import load_dotenv
from database import get_db

from app.security_app import create_jwt_token
import jwt
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse


load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])

class UserData(BaseModel):
    nickName: str


# KAKAO 로그인 함수
@app.get("/kakao/mobile")
async def kakao_callback(code: str):

    # 1. json 코드 
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("KAKAO_REST_API_KEY"),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),
        "redirect_uri": "http://127.0.0.1:8000/auth/kakao/mobile", # [수정] 앱용 Redirect URI
        "code": code,
    }
    
    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    print(f"🔴 카카오 에러 상세: {token_res}")

    if not access_token:
        return JSONResponse(status_code=400, content={"error": "카카오 토큰 발급 실패"})

    user_info_res = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    social_id = str(user_info_res.get("id"))
    user_email = user_info_res.get("kakao_account", {}).get("email", "")

    print(f"social_id:{social_id}")
    print(f"user_email:{user_email}")

    conn = get_db()
    cur = conn.cursor()


    try:
        cur.execute("SELECT nickName FROM users WHERE social_id = %s", (social_id,))
        user_row = cur.fetchone()

        # token 데이터를 json으로 반환
        if user_row is None:
            # 신규 유저일 시 생성 후 즉시 토큰 발급
            cur.execute("INSERT INTO users (social_id, email, nickName) VALUES (%s, %s, NULL)",
            (social_id, user_email, temp_nickName))

            conn.commit()
            return RedirectResponse(url=f"/auth/nickName?email={user_email}")

        token = create_jwt_token(user_email, social_id)
        return {"status": "new_user", "token": token}
    except Exception as e:
        print(f"DB 에러 발생: {e}")
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})
    
    finally:
        cur.close()
        conn.close() 

    
    # 토큰 요청 시 에러가 없는지 먼저 확인
    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    if not access_token:
        print("토큰 발급 실패:", token_res)
        return {"error": "토큰을 받아오지 못했습니다.", "details": token_res}
    

    # 2. Access Token으로 사용자 정보 가져오기 (중요: user_info_res 정의)
    user_info_res = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    print(f"사용자 데이터: {user_info_res}")

    # 데이터 추출
    social_id = str(user_info_res.get("id"))
    kakao_account = user_info_res.get("kakao_account", {})
    user_email = kakao_account.get("email", "")

    conn = get_db()
    cur = conn.cursor()
    try:
        # 3. DB에서 유저 확인 (social_id 기준)
        cur.execute("SELECT nickname FROM users WHERE social_id = %s", (social_id,))
        user_row = cur.fetchone()

        if user_row is None:
            # [신규 유저] DB 저장 후 닉네임 설정 페이지로
            cur.execute("""
                INSERT INTO users (social_id, email, nickname) 
                VALUES (%s, %s, NULL)
            """, (social_id, user_email))
            conn.commit()

            # NICKNAME_REQUIRED => NicknameScreen.tsx
            return { 
                "status": "NICKNAME_REQUIRED",
                "social_id": social_id,
                "email": user_email
            }
        # 닉네임이 있는 경우 정상 로그인
        return{
            "status": "SUCCESS",
            "token": token,
            "email": user_email,
            "nickName": user_row[0]
        }
    finally:
        cur.close()
        conn.close()



# 닉네임 설정 API
@app.post("/set-nickname")
async def set_nickname(
    request : Request, 
    data: UserData,
    ):

    # 미들웨어에서 넘겨주는 이메일 -> kakao, naver 이메일
    email = request.state.user_email 
    nickname = data.nickname

    conn = get_db()
    cur = conn.cursor()
        try:
            # 닉네임 중복체크
            cur.execute("SELECT nickName FROM users WHERE nickName = %s", (nickname,))
            existing_user = cur.fetchone()

            # 다른 사용자와 중복일 경우
            if existing_user and existing_user[0] != email:
            return JSONResponse(
                status_code=400, 
                content={"status": "duplicated", "message": "이미 사용 중인 닉네임입니다."}
            )
            # 2. 닉네임 업데이트
            cur.execute("UPDATE users SET nickname = %s WHERE email = %s", (nickname, email))
            conn.commit()
       

            # 3. 성공 응답 
            return {
                "status": "success",
                "nickname": nickname,
                "email": email
            }
        except Exception as e:
            print(f"❌ 닉네임 저장 에러: {e}")
            return JSONResponse(status_code=500, content={"detail": "서버 오류"})
        finally:
            cur.close()
            conn.close()
        
        
    

