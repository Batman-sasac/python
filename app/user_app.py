import os
import requests
import psycopg2
from fastapi import APIRouter, Response, Cookie, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from dotenv import load_dotenv
from database import get_db

load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])

@app.get("/kakao/callback")
async def kakao_callback(code: str):
    # 1. 인가 코드로 Access Token 받기
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("KAKAO_REST_API_KEY"),
        "client_secret": os.getenv("KAKAO_CLIENT_SECRET"),  
        "redirect_uri": "http://127.0.0.1:8000/auth/kakao/callback",
        "code": code,
    }
    
    # [중요] 토큰 요청 시 에러가 없는지 먼저 확인해야 합니다.
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
            return RedirectResponse(url=f"/auth/nickName?email={user_email}")

        elif not user_row[0]:
            # [닉네임 미설정 유저] 설정 페이지로 이동
            return RedirectResponse(url=f"/auth/nickName?email={user_email}")

        else:
            # [정상 유저] 로그인 완료 및 쿠키 발급
            res = RedirectResponse(url="/index", status_code=303)
            res.set_cookie(key="user_email", value=user_email, httponly=True, path="/")
            return res

    except Exception as e:
        print(f"로그인 처리 중 오류: {e}")
        return {"error": "Internal Server Error"}
    finally:
        cur.close()
        conn.close()

@app.get("/nickName", response_class=HTMLResponse)
async def nickname_page(email: str):
    # 이메일 값이 잘 들어오는지 확인
    print(f"닉네임 설정 페이지 진입 - Email: {email}")
    
    with open("templates/nickName.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/set-nickname")
async def set_nickname(email: str = Form(...), nickname: str = Form(...)):
    conn = get_db()
    cur = conn.cursor()
    try:
        # 이메일을 기준으로 닉네임 업데이트
        cur.execute("UPDATE users SET nickname = %s WHERE email = %s", (nickname, email))
        conn.commit()
        
        # 업데이트 후 로그인 쿠키 발급하며 메인 이동
        res = RedirectResponse(url="/index", status_code=303)
        res.set_cookie(key="user_email", value=email, httponly=True, path="/")
        return res
    finally:
        cur.close()
        conn.close()