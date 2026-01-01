from fastapi import APIRouter, Cookie, Body, HTTPException
from typing import Optional
import psycopg2
import os
from database import get_db

router = APIRouter(prefix="/weekly", tags=["Weekly"])

@router.post("/set-goal")
async def set_study_goal(
    payload: dict = Body(...), 
    user_email: Optional[str] = Cookie(None)
):
    
    target_count = payload.get("target_count")
    if not target_count or int(target_count) < 1:
        return {"status": "error", "message": "올바른 목표 횟수를 입력하세요."}

    conn = get_db()
    cur = conn.cursor()
    try:
        # 기존 목표가 있는지 확인 후 업데이트 또는 삽입 (UPSERT 로직)
        cur.execute("""
            INSERT INTO study_goals (user_email, target_count, is_active)
            VALUES (%s, %s, TRUE)
            ON CONFLICT (user_email) 
            DO UPDATE SET target_count = EXCLUDED.target_count, created_at = CURRENT_TIMESTAMP;
        """, (user_email, int(target_count)))
        
        # 참고: ON CONFLICT를 쓰려면 user_email에 UNIQUE 제약조건이 있어야 합니다.
        # 없다면 DELETE 후 INSERT 하는 방식으로 처리하세요.
        
        conn.commit()
        return {"status": "success", "message": f"주간 목표가 {target_count}회로 설정되었습니다!"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()


@app.get("/setting", response_class=HTMLResponse)
async def index_page(user_email: Optional[str] = Cookie(None)): # 변수명 확인!
    print(f"현재 브라우저에서 넘어온 쿠키 값: {user_email}") # 서버 터미널에 출력됨
    
    with open("templates/weeklyTarget.html", "r", encoding="utf-8") as f:
        return f.read()