from fastapi import APIRouter, UploadFile, File
from pydantic import BaseModel
from typing import List
import os
from core.gpt_service import GPTService

app = APIRouter(tags=["OCR"])

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
gpt_service = GPTService(API_KEY)

class QuizSaveRequest(BaseModel):
    subject_name: str
    original: str
    quiz: str
    answers: List[str]


@app.post("/ocr")
async def run_ocr_endpoint(file: UploadFile = File(...)):
    try:
        # 1. 파일 데이터 읽기
        file_bytes = await file.read()
        
        # 2. 이미지/PDF 통합 처리 함수 호출
        extracted_text = gpt_service.process_file(file_bytes, file.filename)
        
        return {"status": "success", "text": extracted_text}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/save-test")
async def save_test(data: QuizSaveRequest):
    # DB 저장 대신 터미널에 데이터를 예쁘게 출력합니다.

from fastapi import APIRouter, UploadFile, File, Cookie, Form, Body
from pydantic import BaseModel
from typing import List, Optional
import os
from core.gpt_service import GPTService
from database import get_db  # 분리한 database.py에서 가져옴

app = APIRouter(tags=["OCR"]) # app 대신 router로 통일 (main.py 연동용)

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
gpt_service = GPTService(API_KEY)

# JSON 데이터를 위한 Pydantic 모델
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

# 2. OCR 결과 및 퀴즈 데이터 DB 저장 엔드포인트 (JSON 방식 통합)
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
        # DB 저장 로직 (ocr_data 테이블)
        cur.execute("""
            INSERT INTO ocr_data (user_email, subject_name, ocr_text, blank_text) 
            VALUES (%s, %s, %s, %s)
        """, (user_email, data.subject_name, data.original, data.quiz))
        
        conn.commit()

        # 터미널 예쁘게 출력 (디버깅용)
        print("\n" + "="*50)
        print(f"📧 사용자: {user_email}")
        print(f"📂 과목명: {data.subject_name}")
        print(f"📝 원본 길이: {len(data.original)}자")
        print(f"❓ 빈칸 텍스트: {data.quiz[:50]}...") 
        print(f"✅ 추출된 정답 배열: {data.answers}")
        print("="*50 + "\n")

        return {"status": "success", "message": "OCR 자료가 DB에 저장되었습니다."}

    except Exception as e:
        conn.rollback() # 에러 발생 시 롤백
        print(f"❌ 저장 에러: {e}")
        return {"status": "error", "message": "데이터 저장 실패"}
    finally:
        cur.close()
        conn.close()
    @app.post("/save-data")
    async def save_ocr_result(
    subject: str = Form(...),
    original_text: str = Form(...),
    blank_text: str = Form(...),
    user_email: Optional[str] = Cookie(None)  # 쿠키에서 이메일 가져오기
):
   
    conn = get_db()
    cur = conn.cursor()
    try:
        # ocr_data 테이블에 원본과 빈칸 데이터 저장
        # (테이블에 blank_text 컬럼이 없다면 ALTER TABLE ocr_data ADD COLUMN blank_text TEXT; 실행 필요)
        cur.execute("""
            INSERT INTO ocr_data (user_email, subject_name, ocr_text, blank_text) 
            VALUES (%s, %s, %s, %s)
        """, (user_email, subject, original_text, blank_text))
        
        conn.commit()

        print("\n" + "="*50)
        print(f"📂 과목명: {data.subject_name}")
        print(f"📝 원본 길이: {len(data.original)}자")
        print(f"❓ 빈칸 텍스트: {data.quiz[:50]}...") # 앞부분만 출력
        print(f"✅ 추출된 정답 배열: {data.answers}")
        print("="*50 + "\n")


        return {"status": "success", "message": "OCR 자료가 저장되었습니다."}
    except Exception as e:
        print(f"저장 에러: {e}")
        return {"error": "데이터 저장 실패"}
    finally:
        cur.close()
        conn.close()