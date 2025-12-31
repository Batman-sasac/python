import os
import requests
import psycopg2
from fastapi import APIRouter, Response , Cookie

from fastapi.responses import RedirectResponse
from dotenv import load_dotenv

load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])

# DB 연결 설정
def get_db():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS")
    )

@app.get("/kakao/callback")
async def kakao_callback(code: str, response: Response):
    # 1. 인가 코드로 Access Token 받기
    token_url = "https://kauth.kakao.com/oauth/token"
    token_data = {
        "grant_type": "authorization_code",
        "client_id": os.getenv("KAKAO_REST_API_KEY"),
        "redirect_uri": "http://127.0.0.1:8000/auth/kakao/callback",
        "code": code,
    }
    token_res = requests.post(token_url, data=token_data).json()
    access_token = token_res.get("access_token")

    # 2. Access Token으로 사용자 정보 가져오기
    user_info_res = requests.get(
        "https://kapi.kakao.com/v2/user/me",
        headers={"Authorization": f"Bearer {access_token}"}
    ).json()

    social_id = str(user_info_res.get("id"))
    nickname = user_info_res.get("properties", {}).get("nickname")
    email = user_info_res.get("kakao_account", {}).get("email", "")

    # 3. DB에 사용자 저장 (이미 있으면 무시, 없으면 추가)
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO users (social_id, nickname, email) 
            VALUES (%s, %s, %s)
            ON CONFLICT (social_id) DO UPDATE SET nickname = EXCLUDED.nickname
            RETURNING id;
        """, (social_id, nickname, email))
        user_internal_id = cur.fetchone()[0]
        conn.commit()

        # 4. 로그인 성공 -> index.html로 리다이렉트하며 쿠키 설정
        # HttpOnly 쿠키로 보안을 강화합니다.
        redirect = RedirectResponse(url="/index", status_code=303)
        redirect.set_cookie(key="session_user", value=str(user_internal_id), httponly=True)
        return redirect

    except Exception as e:
        print(f"Error: {e}")
        return {"message": "로그인 중 오류 발생"}
    finally:
        cur.close()
        conn.close()