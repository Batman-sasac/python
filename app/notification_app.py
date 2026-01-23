from fastapi import APIRouter, Body, Request
from pydantic import BaseModel
from typing import Optional
from database import get_db
from core.notification_service import scheduler

app = APIRouter()






@app.on_event("startup")
def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        print("🚀 복습 알림 스케줄러가 가동되었습니다.")

@app.on_event("shutdown")
def shutdown_event():
    try:
        if scheduler.running: # 스케줄러가 실행 중인지 확인
            scheduler.shutdown()
            print("🚀 스케줄러가 안전하게 종료되었습니다.")
    except SchedulerNotRunningError:
        print("⚠️ 스케줄러가 이미 종료되었거나 실행 중이 아닙니다.")

# 복습 알림 
@app.post("/notification-push/update")
async def update_notification(
    payload: dict = Body(...), 
    request: Request
):

    user_email = request.state.user_email

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