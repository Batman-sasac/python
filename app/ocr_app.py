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
    print("\n" + "="*50)
    print(f"📂 과목명: {data.subject_name}")
    print(f"📝 원본 길이: {len(data.original)}자")
    print(f"❓ 빈칸 텍스트: {data.quiz[:50]}...") # 앞부분만 출력
    print(f"✅ 추출된 정답 배열: {data.answers}")
    print("="*50 + "\n")
    
    return {
        "status": "success", 
        "message": f"[{data.subject_name}] 데이터가 서버에 잘 도착했습니다!",
        "received_data": data
    }