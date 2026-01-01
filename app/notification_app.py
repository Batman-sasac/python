from fastapi import APIRouter, Body, Cookie, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse
from typing import Optional
from database import get_db
from core.notification_service import scheduler

app = APIRouter()


@app.get("/notification", response_class=HTMLResponse)
async def index_page(): 
    
    with open("templates/notification.html", "r", encoding="utf-8") as f:
        return f.read()



@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("🚀 복습 알림 스케줄러가 가동되었습니다.")

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()
    print("🛑 스케줄러가 종료되었습니다.")

# 복습 알림 
@app.post("/update")
async def update_notification(
    payload: dict = Body(...), 
    user_email: str = Cookie(None)
):
    is_notify = payload.get("is_notify")
    remind_time = payload.get("remind_time") # "07:30" 형식

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE users 
            SET is_notify = %s, remind_time = %s 
            WHERE email = %s
        """, (is_notify, remind_time, user_email))
        conn.commit()
        print(f"알림 설정 완료:{remind_time}")
        return {"status": "success", "message": "알림 설정이 저장되었습니다."}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()