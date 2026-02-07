# ocr 및 빈칸/원본 저장
#
# DB(ocr_data) 실제 컬럼: ocr_text, answers, user_answers, quiz_html (모두 jsonb)
# - ocr_text (jsonb): { "pages": [...], "blanks": [...], "quiz": {} }
# - answers (jsonb): 정답 배열 [ "단어1", "단어2", ... ]
# - user_answers (jsonb): 사용자 작성 답변 [ "답1", "답2", ... ]
# - quiz_html (jsonb): 퀴즈 메타 { "raw": "..." }

import json
from fastapi import APIRouter, UploadFile, File, Form, Body, Depends, Query
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, Union
import os
from database import supabase

from core.clova_ocr_service import CLOVAOCRService


from core.ocr_usage_service import (
    OCR_PAGE_LIMIT,
    estimate_page_count,
    get_user_ocr_usage,
    add_ocr_usage,
    check_can_use,
)


from app.security.security_app import get_current_user

app = APIRouter(tags=["OCR"])

# GPT 서비스 초기화
API_KEY = os.getenv("OPENAI_API_KEY")
clova_service = CLOVAOCRService(API_KEY)


class PageItem(BaseModel):
    original_text: str
    keywords: List[str] = []


class BlankItem(BaseModel):
    blank_index: int
    word: str
    page_index: int = 0


# JSON 요청 모델: 페이지·빈칸·사용자 답변 모두 JSON으로
class QuizSaveRequest(BaseModel):
    subject_name: str
    study_name: Optional[str] = None
    # 페이지별 데이터 (필수 시 pages, 단일 페이지 시 original+answers 호환)
    pages: Optional[List[PageItem]] = None
    original: Optional[str] = None
    answers: Optional[List[str]] = None
    # 빈칸 정의 (blank_index 순서 = user_answers 인덱스)
    blanks: Optional[List[BlankItem]] = None
    # 사용자 작성 답변 (빈칸 순서대로)
    user_answers: Optional[List[str]] = None
    quiz: Optional[Union[Dict[str, str], str]] = None


# OCR 사용량 조회 API (50회 도달 시 한도 메시지 반환)
@app.get("/ocr/usage")
async def get_ocr_usage(email: str = Depends(get_current_user)):
    """
    회원의 OCR 사용량 조회.
    pages_used >= 50 이면 "이용가능한 무료 횟수를 다 사용하셨습니다" 반환.
    """
    used = get_user_ocr_usage(email)
    remaining = max(0, OCR_PAGE_LIMIT - used)

    if used >= OCR_PAGE_LIMIT:
        return {
            "status": "limit_reached",
            "message": "이용가능한 무료 횟수를 다 사용하셨습니다",
            "pages_used": used,
            "pages_limit": OCR_PAGE_LIMIT,
            "remaining": 0,
        }
    return {
        "status": "ok",
        "pages_used": used,
        "pages_limit": OCR_PAGE_LIMIT,
        "remaining": remaining,
    }


# 예상 소요 시간 반환
@app.post("/ocr/estimate")
async def get_estimate(file: UploadFile = File(...)):
    # 가볍게 파일 정보만 읽어서 시간 계산
    file_bytes = await file.read()

    files_data = []
    for file in files:
        content = await file.read()
        files_data.append({"filename": file.filename, "bytes": content})
    
    result_msg = service.get_estimation_message(files_data)
    
    return {"estimated_time": result_msg}

# 1. OCR 텍스트 추출 엔드포인트
@app.post("/ocr")
async def run_ocr_endpoint(
    file: UploadFile = File(...),
    email: str = Depends(get_current_user),
):
    try:
        file_bytes = await file.read()

        # 사용량 한도 체크 (OCR 호출 전)
        estimated = estimate_page_count(file_bytes, file.filename or "")
        can_use, used = check_can_use(email, estimated)
        if not can_use:
            return {
                "status": "limit_reached",
                "message": "이용가능한 무료 횟수를 다 사용하셨습니다",
                "pages_used": used,
                "pages_limit": OCR_PAGE_LIMIT,
            }

        # 네이버 OCR로 텍스트 추출
        result = clova_service.process_file(file_bytes, file.filename)
        print(f"ocr 결과:{result}")

        if result["status"] == "error":
            return result

        # 사용량 DB 저장
        page_count = result.get("page_count", 1)
        add_ocr_usage(email, page_count)

        return {"status": "success", "data": result}

    except Exception as e:
        print(f"서버 내부 에러: {e}")
        return {"status": "error", "message": str(e)}


# 2. OCR 결과 및 퀴즈 데이터 DB 저장 (페이지·빈칸·답변 모두 JSON)
@app.post("/ocr/save-test")
async def save_test(data: QuizSaveRequest, email: str = Depends(get_current_user)):
    print(f"저장 요청 유저: {email}")

    try:
        # 페이지별 원문·키워드 (pages 있으면 사용, 없으면 original+answers로 1페이지)
        if data.pages and len(data.pages) > 0:
            pages_data = [{"original_text": p.original_text, "keywords": p.keywords or []} for p in data.pages]
        else:
            orig = data.original or ""
            kw = data.answers or []
            pages_data = [{"original_text": orig, "keywords": kw}]

        # 빈칸 정의 (blanks 있으면 사용, 없으면 keywords 순서로 생성)
        if data.blanks and len(data.blanks) > 0:
            blanks_data = [
                {"blank_index": b.blank_index, "word": b.word, "page_index": b.page_index}
                for b in data.blanks
            ]
        else:
            blanks_data = []
            for pi, page in enumerate(pages_data):
                for ki, w in enumerate(page["keywords"]):
                    blanks_data.append({"blank_index": len(blanks_data), "word": w, "page_index": pi})

        quiz_val = data.quiz if isinstance(data.quiz, dict) else ({"raw": data.quiz} if data.quiz else {})

        # DB 실제 컬럼명: ocr_text, answers, user_answers, quiz_html (jsonb)
        ocr_text_json: Dict[str, Any] = {
            "pages": pages_data,
            "blanks": blanks_data,
            "quiz": quiz_val,
        }
        answers_json: List[str] = [b["word"] for b in blanks_data]
        user_answers_list: List[str] = list(data.user_answers) if data.user_answers else []

        insert_data = {
            "user_email": email,
            "subject_name": data.subject_name,
            "study_name": data.study_name or data.subject_name or "",
            "ocr_text": ocr_text_json,
            "answers": answers_json,
            "user_answers": user_answers_list,
            "quiz_html": quiz_val,
        }

        response = (
            supabase.table("ocr_data")
            .insert(insert_data)
            .execute()
        )

        if not response.data:
            return {"status": "error", "message": "저장 후 ID를 받지 못했습니다."}

        new_id = response.data[0]["id"]
        print("\n" + "✅" * 10 + " OCR 데이터 저장 성공 " + "✅" * 10)
        print(f"ID        : {new_id}")
        print(f"사용자    : {email}")
        print(f"과목명    : {data.subject_name}")
        print(f"페이지 수 : {len(pages_data)}")
        print(f"빈칸 수   : {len(blanks_data)}")
        print("=" * 45 + "\n")

        return {"status": "success", "quiz_id": new_id}
    except Exception as e:
        print(f"저장 에러: {e}")
        return {"status": "error", "message": str(e)}


# 복습 시 퀴즈 데이터 JSON으로 가져오기 (앱에서 ScaffoldingPayload 형태로 사용)
@app.get("/ocr/quiz/{quiz_id}")
async def get_quiz_for_review(quiz_id: int, email: str = Depends(get_current_user)):
    try:
        res = (
            supabase.table("ocr_data")
            .select("id, subject_name, study_name, ocr_text, user_answers")
            .eq("id", quiz_id)
            .eq("user_email", email)
            .single()
            .execute()
        )
        if not res.data:
            return {"status": "error", "message": "데이터를 찾을 수 없습니다."}

        row = res.data
        ocr_val = row.get("ocr_text") or {}
        pages = ocr_val.get("pages", [])
        blanks = ocr_val.get("blanks", [])
        quiz_val = ocr_val.get("quiz") or {}
        raw_text = quiz_val.get("raw", "") if isinstance(quiz_val, dict) else str(quiz_val)

        # 원문: pages[0].original_text 또는 quiz.raw, 여러 페이지면 \n\n으로 이어붙임
        if pages:
            extracted_text = "\n\n".join(p.get("original_text", "") for p in pages)
        else:
            extracted_text = raw_text

        # 빈칸 목록: blanks 있으면 사용, 없으면 pages[].keywords로 생성
        if blanks:
            blanks_list = [{"id": b.get("blank_index", i), "word": b.get("word", ""), "meaningLong": ""} for i, b in enumerate(blanks)]
        else:
            kw_list = []
            for p in pages:
                kw_list.extend(p.get("keywords") or [])
            blanks_list = [{"id": i, "word": w, "meaningLong": ""} for i, w in enumerate(kw_list)]

        user_answers = row.get("user_answers") or []

        return {
            "status": "success",
            "data": {
                "quiz_id": row.get("id"),
                "title": row.get("study_name") or row.get("subject_name") or "학습 자료",
                "extractedText": extracted_text,
                "blanks": blanks_list,
                "user_answers": user_answers,
            },
        }
    except Exception as e:
        print(f"퀴즈 조회 에러: {e}")
        return {"status": "error", "message": str(e)}


# 해당 학습 삭제 로직 /ocr/ocr-data/delete/{학습파일 번호}
@app.delete("/ocr/ocr-data/delete/{quiz_id}")
async def delete_ocr_data(quiz_id: int, email: str = Depends(get_current_user)):
    print(f"삭제 요청 유저: {email}")

    try:
        res = (
            supabase.table("ocr_data")
            .select("image_url")
            .eq("id", quiz_id)
            .eq("user_email", email)
            .execute()
        )

        if not res.data:
            return {"status": "error", "message": "데이터를 찾지 못했습니다"}

        file_path = res.data[0].get("image_url")
        if file_path and os.path.exists(file_path):
            os.remove(file_path)

        # 2. 데이터 삭제
        (
            supabase.table("ocr_data")
            .delete()
            .eq("id", quiz_id)
            .eq("user_email", email)
            .execute()
        )
        
        return {"status": "success", "message": "삭제 성공했습니다."}

    # try 블록 안에서 에러가 발생하면 이쪽으로 넘어옵니다.
    except Exception as e:
        print(f"Error occurred: {e}") # 로그를 위해 추가하는 것을 추천합니다.
        return {"status": "error", "message": str(e)}


# 학습 목록 /ocr/list
@app.get("/ocr/list")
async def get_ocr_list(
    email: str = Depends(get_current_user),
):
    print(f"학습 목록 요청 유저: {email}")


    try:
        response = (
            supabase.table("ocr_data")
            .select("id, study_name, subject_name, ocr_text, created_at")
            .eq("user_email", email)
            .order("created_at", desc=True)
            .execute()
        )

        formatted_data = []
        for item in response.data:
            ocr_val = item.get("ocr_text") or {}
            pages = ocr_val.get("pages", [])
            first_text = pages[0].get("original_text", "") if pages else ""
            ocr_str = (first_text[:50] + "...") if len(first_text) > 50 else first_text
            formatted_data.append({
                "id": item["id"],
                "study_name": item.get("study_name", ""),
                "subject_name": item.get("subject_name", ""),
                "ocr_preview": ocr_str,
                "created_at": item.get("created_at"),
            })

        return {
            "data": formatted_data
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}



        
