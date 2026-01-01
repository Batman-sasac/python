from fastapi import APIRouter, UploadFile, File, Cookie, Form, Body
from pydantic import BaseModel
from typing import List, Optional
import os
from core.gpt_service import GPTService
from database import get_db  

app = APIRouter(tags=["OCR"])

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
gpt_service = GPTService(API_KEY)

# JSON 요청을 위한 모델
class QuizSaveRequest(BaseModel):
    subject_name: str
    original: str
    quiz: str
    answers: List[str]

# 1. OCR 텍스트 추출 엔드포인트
@app.post("/ocr")
async def run_ocr_endpoint(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        extracted_text = gpt_service.process_file(file_bytes, file.filename)
        return {"status": "success", "text": extracted_text}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# 2. OCR 결과 및 퀴즈 데이터 DB 저장 (JSON 방식)
@app.post("/save-test")
async def save_test(
    data: QuizSaveRequest, 
    user_email: Optional[str] = Cookie(None)
):
    conn = get_db()
    if not conn:
        return {"status": "error", "message": "데이터베이스 연결 실패"}
    
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ocr_data (user_email, subject_name, ocr_text, blank_text) 
            VALUES (%s, %s, %s, %s)
        """, (user_email, data.subject_name, data.original, data.quiz))
        
        conn.commit()

        print("\n" + "="*50)
        print(f"📧 사용자: {user_email}")
        print(f"📂 과목명: {data.subject_name}")
        print(f"📝 원본 길이: {len(data.original)}자")
        print("="*50 + "\n")

        return {"status": "success", "message": "OCR 자료가 DB에 저장되었습니다."}
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ 저장 에러: {e}")
        return {"status": "error", "message": "데이터 저장 실패"}
    finally:
        cur.close()
        conn.close()

# 3. [추가] 복습 알림 설정 저장 엔드포인트 (users 테이블 업데이트)
@app.post("/update-notification")
async def update_notification(
    payload: dict = Body(...), 
    user_email: Optional[str] = Cookie(None)
):
    # 미들웨어가 통과시켰다면 user_email은 존재함
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
        return {"status": "success", "message": "복습 알림 설정이 저장되었습니다."}
    except Exception as e:
        if conn: conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()