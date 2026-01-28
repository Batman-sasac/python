from fastapi import APIRouter, Request, Body
from database import get_db

app = APIRouter()

#users DB fcm_token 저장
@app.post("/user/update-fcm-token")
async def update_fcm_token(request: Request, payload: dict = Body(...)):
    user_email = request.state.user_email # 미들웨어에서 추출
    fcm_token = payload.get("fcm_token")
    
    if not fcm_token:
        return {"status": "error", "message": "토큰이 없습니다."}

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users SET fcm_token = %s 
            WHERE email = %s
        """, (fcm_token, user_email))
        conn.commit()
        return {"status": "success", "message": "FCM 토큰이 업데이트되었습니다."}
    finally:
        cur.close()
        conn.close()