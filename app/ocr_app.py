# ocr 및 빈칸/원본 저장

from fastapi import APIRouter, UploadFile, File, Cookie, Form, Body
from pydantic import BaseModel
from typing import List, Optional
import os
# from core.gpt_service import GPTService
from database import get_db  
from core.clova_ocr_service import CLOVAOCRService

app = APIRouter(tags=["OCR"])

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
clova_service = CLOVAOCRService(API_KEY)


# JSON 요청을 위한 모델
class QuizSaveRequest(BaseModel):
    subject_name: str
    original: str
    quiz: str
    answers: Optional[List[str]] = []

# 1. OCR 텍스트 추출 엔드포인트 수정
@app.post("/ocr")
async def run_ocr_endpoint(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()

        # 1. 네이버 OCR로 텍스트 추출
        result = clova_service.process_file(file_bytes, file.filename)
        
        if result["status"] == "error":
            return result

        # 2. 프론트엔드 JS가 data.keywords를 사용하므로 키 이름을 일치시켜 반환
        return result
    
    except Exception as e:
        print(f"서버 내부 에러: {e}")
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

        print("\n" + "✅"*10 + " OCR 데이터 저장 성공 " + "✅"*10)
        print(f"ID      : {new_id}")
        print(f"사용자  : {user_email}")
        print(f"과목명  : {data.subject_name}")
        print(f"키워드수: {len(data.answers)}개")
        print(f"🔹 원본 내용 미리보기: {data.original}")
        print("="*45 + "\n")
        

        return {"status": "success", "quiz_id": new_id}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()
