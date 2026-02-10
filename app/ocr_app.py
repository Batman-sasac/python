# ocr 및 빈칸/원본 저장

import json
from fastapi import APIRouter, UploadFile, File, Form, Body, Request
from pydantic import BaseModel
from typing import Dict, List, Optional
import os
from database import supabase 
from core.clova_ocr_service import CLOVAOCRService

app = APIRouter(tags=["OCR"])

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
clova_service = CLOVAOCRService(API_KEY)


# JSON 요청을 위한 모델
class QuizSaveRequest(BaseModel):
    subject_name: str
    study_name: str
    original_text: List[str]
    quiz: Optional[Dict[str, str]] = None
    answers: Optional[List[str]] = []


# 예상 소요 시간 반환 (현재 미사용)
# @app.post("/ocr/estimate")
# async def get_estimate(file: UploadFile = File(...)):
#     file_bytes = await file.read()
#     files_data = [{"filename": file.filename, "bytes": file_bytes}]
#     result_msg = clova_service.get_estimation_message(files_data)
#     return {"estimated_time": result_msg}

# OCR 사용량 조회 엔드포인트
@app.get("/ocr/usage")
async def get_ocr_usage(request: Request):
    user_email = request.state.user_email
    
    try:
        # 사용자 OCR 사용량 조회
        user = supabase.table("users").select("ocrpages_used").eq("email", user_email).single().execute()
        
        pages_used = user.data.get("ocrpages_used", 0) if user.data else 0
        pages_limit = 50  # 월 무료 한도
        remaining = max(0, pages_limit - pages_used)
        
        return {
            "status": "success",
            "pages_used": pages_used,
            "pages_limit": pages_limit,
            "remaining": remaining,
            "message": f"이번 달 남은 OCR 횟수: {remaining}/{pages_limit}"
        }
    except Exception as e:
        print(f"OCR 사용량 조회 오류: {e}")
        return {"status": "error", "message": str(e)}


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
        return {
        "status": "success",
        "data": result
    }
    
    except Exception as e:
        print(f"서버 내부 에러: {e}")
        return {"status": "error", "message": str(e)}


# 2. OCR 결과 및 퀴즈 데이터 DB 저장 (JSON 방식) 
@app.post("/ocr/save-test")
async def save_test(data: QuizSaveRequest,
request: Request):

    user_email = request.state.user_email
    print(f"user_email:{user_email}")

   
    try:
        insert_data = {
            "user_email": user_email,
            "subject_name": data.subject_name,
            "study_name": data.study_name,
            "ocr_text": data.original_text,   # 리스트 그대로 저장
            "answers": data.answers or [],     # 리스트 그대로 저장
            "quiz_html": data.quiz or {}      # 딕셔너리 그대로 저장
        }

        response = supabase.table("ocr_data").insert(insert_data).execute()
        
        new_id = response.data[0]['id']

        print("\n" + "✅"*10 + " OCR 데이터 저장 성공 " + "✅"*10)
        print(f"ID      : {new_id}")
        print(f"사용자  : {user_email}")
        print(f"과목명  : {data.subject_name}")
        print(f"키워드수: {len(data.answers or [])}개")
        print("="*45 + "\n")

        return {"status": "success", "quiz_id": new_id}
    except Exception as e:
        print(f"저장 에러: {e}")
        return {"status": "error", "message": str(e)}


# 해당 학습 삭제 로직 /ocr/ocr-data/delete/{학습파일 번호}
@app.delete("/ocr/ocr-data/delete/{quiz_id}")
async def delete_ocr_data(request: Request,
quiz_id: int):

    user_email = request.state.user_email
    print(f"user_email:{user_email}")

    try:
        # 1. 이미지 경로 확인
        res = ( 
            supabase.table("ocr_data")
            .select("image_url") 
            .eq("id", quiz_id)
            .eq("user_email", user_email) 
            .execute()
        )

        if not res.data:
            return {"status": "error", "message": "데이터를 찾지 못했습니다"}

        file_path = res.data[0].get("image_url")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # 2. 데이터 삭제
        supabase.table("ocr_data").delete().eq("id", quiz_id).eq("user_email", user_email).execute()
        
        return {"status": "success", "message": "삭제 성공했습니다."}

    # try 블록 안에서 에러가 발생하면 이쪽으로 넘어옵니다.
    except Exception as e:
        print(f"Error occurred: {e}") # 로그를 위해 추가하는 것을 추천합니다.
        return {"status": "error", "message": str(e)}


# 복습용 퀴즈 데이터 조회 /ocr/quiz/{quiz_id}
@app.get("/ocr/quiz/{quiz_id}")
async def get_quiz_for_review(request: Request, quiz_id: int):
    user_email = request.state.user_email
    
    try:
        response = supabase.table("ocr_data") \
            .select("*") \
            .eq("id", quiz_id) \
            .eq("user_email", user_email) \
            .single() \
            .execute()
        
        if not response.data:
            return {"status": "error", "message": "퀴즈를 찾을 수 없습니다."}
        
        data = response.data
        
        # DB 형식을 프론트엔드 ScaffoldingPayload 형식으로 변환
        ocr_text_list = data.get("ocr_text", [])
        answers_list = data.get("answers", [])
        
        # 텍스트 합치기
        extracted_text = "\n\n".join(ocr_text_list) if isinstance(ocr_text_list, list) else str(ocr_text_list)
        
        # blanks 배열 생성
        blanks = []
        if isinstance(answers_list, list):
            for idx, word in enumerate(answers_list):
                blanks.append({
                    "id": idx,
                    "word": str(word),
                    "meaningLong": f"{word}의 뜻"
                })
        
        return {
            "status": "success",
            "data": {
                "quiz_id": data["id"],
                "title": data.get("subject_name", "") or data.get("study_name", "학습 자료"),
                "extractedText": extracted_text,
                "blanks": blanks,
                "user_answers": data.get("user_answers", [])
            }
        }
    except Exception as e:
        print(f"퀴즈 조회 오류: {e}")
        return {"status": "error", "message": str(e)}


# 학습 목록 /ocr/list
from fastapi import Query, Cookie

# 학습 목록 /ocr/list
@app.get("/ocr/list")
async def get_ocr_list(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1)
):
    user_email = request.state.user_email

    start = (page - 1) * size
    end = start + size - 1

    try:
        # PostgreSQL의 복잡한 CASE 문은 RPC(함수)를 쓰거나 
        # 원본 데이터를 가져온 뒤 파이썬에서 가공하는 것이 SDK에서 더 깔끔합니다.
        response = supabase.table("ocr_data") \
            .select("id, study_name, subject_name, ocr_text, created_at") \
            .eq("user_email", user_email) \
            .order("created_at", desc=True) \
            .range(start, end) \
            .execute()

        # 데이터 가공 (미리보기 및 날짜 표시)
        formatted_data = []
        for item in response.data:
            ocr_str = str(item['ocr_text'])
            formatted_data.append({
                "id": item['id'],
                "study_name": item['study_name'],
                "subject_name": item['subject_name'],
                "ocr_preview": (ocr_str[:50] + "...") if len(ocr_str) > 50 else ocr_str,
                "created_at": item['created_at'] # 날짜 포맷팅은 필요시 파이썬에서 추가
            })

        return {
            "page": page,
            "size": size,
            "data": formatted_data
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



        
