from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from core.gpt_service import GPTService
from pydantic import BaseModel
from typing import List
import base64
import uvicorn
import os
from dotenv import load_dotenv

app = FastAPI()

# 브라우저 통신 허용 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()
API_KEY = os.getenv("OPENAI_API_KEY")
gpt_service = GPTService(API_KEY)

@app.get("/", response_class=HTMLResponse)
async def read_index():
    # 경로를 'templates/index.html'로 지정합니다.
    file_path = os.path.join("templates", "index.html")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"<h1>에러: {file_path} 파일을 찾을 수 없습니다.</h1>"

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



# 저장 테스트를 위한 데이터 모델
class QuizSaveRequest(BaseModel):
    subject_name: str
    original: str
    quiz: str
    answers: List[str]  # 드래그한 정답 리스트

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


if __name__ == "__main__":
    host = "127.0.0.1"
    port = 8000
    print(f"\n🚀 서버 가동 중: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)