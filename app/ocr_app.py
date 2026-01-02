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
    answers: Optional[List[str]] = []

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
@app.post("/ocr/save-test")
async def save_test(data: QuizSaveRequest, user_email: Optional[str] = Cookie(None)):
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO ocr_data (user_email, subject_name, ocr_text, blank_text, answers) 
            VALUES (%s, %s, %s, %s, %s) RETURNING id
        """, (user_email, data.subject_name, data.original, data.quiz, data.answers))
        new_id = cur.fetchone()[0]
        conn.commit()
        return {"status": "success", "quiz_id": new_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()
