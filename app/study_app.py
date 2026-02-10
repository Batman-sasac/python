# 재첨 후 정답 저장 

from fastapi import APIRouter, HTTPException, Body, Depends, Form
from pydantic import BaseModel
from typing import List, Optional
from database import supabase
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.security.security_app import get_current_user

app = APIRouter(prefix="/study", tags=["study"])

# 퀴즈 제출 모델
class QuizSubmitRequest(BaseModel):
    quiz_id: int                # 퀴즈 번호 
    user_answers: List[str]          # 유저 답변 리스트
    correct_answers: List[str]      # 빈칸 답변 리스트
    grade_cnt: int                  # 채점 횟수 
    original_text: list[str]              # 원문 텍스트
    keywords: List[str]             # 키워드 리스트
    quiz_html: str                        # 퀴즈 메타 데이터



# 채점 버튼 클릭 시 리워드 제공 &ocr_data 저장
@app.post("/grade")
async def grade_quiz(
    email: str = Depends(get_current_user),
    payload: QuizSubmitRequest = Body(...)
):
    print(f"채점할 유저:{email}")
    
    # 1. 전달받은 데이터 추출 (이름을 payload로 통일)
    correct_ans = payload.get('answer', [])
    user_ans = payload.get('user_answers', [])
    quiz_id = payload.get('quiz_id')

    if not correct_ans or not email:
        return {"status": "error", "message": "필수 데이터가 누락되었습니다."}


    try:
        # [1] ocr_data 저장 (JSONB 자동 처리)
        supabase.table("ocr_data") \
            .insert({
                "user_email": email,
                "quiz_id": quiz_id,
                "user_answers": user_ans,
                "answers": correct_ans,
                "original_text": original_text,
                "keywords": keywords,
                "quiz_html": quiz_html}) \
            .eq("id", quiz_id) \
            .eq("user_email", email).execute()

        # [2] 학습 로그 기록
        supabase.table("study_logs").insert({
            "quiz_id": quiz_id, 
            "user_email": email
        }).execute()

        # [3] 리워드 지급 (grade_cnt > 0 일 때만)
        if grade_cnt > 0:
            supabase.table("reward_history").insert({
                "user_email": email,
                "reward_amount": grade_cnt*2,
                "reason": f"초기 학습을 통학 리워드: {grade_cnt}개 정답"
            }).execute()

            # 포인트 합산 (현재 포인트 조회 후 업데이트)
            user_res = supabase.table("users").select("points").eq("email", email).single().execute()
            new_points = (user_res.data.get("points") or 0) + grade_cnt*2
            supabase.table("users").update({"points": new_points}).eq("email", email).execute()

        return {
            "status": "success",
            "score": grade_cnt, # 맞은 갯수
            "reward_given": grade_cnt*2, # 리워드 금액
            "new_points": new_points # 새로운 포인트
        }
    except Exception as e:
        print(f"오류: {e}")
        return {"status": "error", "message": str(e)}

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# 복습화면
@app.get("/review_study/{quiz_id}", response_class=HTMLResponse)
async def review_page(
    quiz_id: int,
    email: str = Depends(get_current_user)
    ):


    
    print(f"복습화면:{email}")
    print(f"복습 번호:{quiz_id}")

    try:
        # DB: ocr_text (jsonb) = { pages, blanks, quiz }, answers (jsonb) = 정답 배열
        res = supabase.table("ocr_data") \
            .select("id, subject_name, study_name, ocr_text, answers, user_answers, quiz_html") \
            .eq("id", quiz_id) \
            .eq("user_email", email) \
            .single().execute()

        row = res.data
        ocr_val = row.get("ocr_text") or {}
        pages = ocr_val.get("pages", [])
        blanks = ocr_val.get("blanks", [])
        # blanks 없으면 pages[].keywords를 순서대로 사용 (저장 형식 호환)
        if blanks:
            answers_list = [b.get("word", "") for b in blanks]
        else:
            answers_list = []
            for p in pages:
                answers_list.extend(p.get("keywords") or [])
        quiz_data = {
            "id": row.get("id"),
            "subject_name": row.get("subject_name"),
            "study_name": row.get("study_name"),
            "ocr_text": [p.get("original_text", "") for p in pages],
            "answers": row.get("answers"),
            "user_answers": row.get("user_answers"),
            "quiz_html": row.get("quiz_html"),
        }

        return templates.TemplateResponse("review_study.html", {
            "request": request,
            "quiz": quiz_data,
            "quiz_json": json.dumps(quiz_data, ensure_ascii=False)
        })
    except Exception:
        return HTMLResponse(content="데이터를 찾을 수 없습니다.", status_code=404)


# 복습 완료 시 리워드 제공 & 사용자 답변 저장
@app.post("/review-study")
async def review_study_reward(request: Request, email: str = Depends(get_current_user)):
    print(f"복습 완료 시 리워드 제공 유저:{email}")

    data = await request.json()
    quiz_id = data.get("quiz_id")
    all_user_answers = data.get("user_answers")

    try:
        # DB: answers (jsonb) 컬럼에 정답 배열 저장됨
        res = supabase.table("ocr_data").select("answers").eq("id", quiz_id).single().execute()
        correct_answers = res.data.get("answers") or []

        # 채점
        score = sum(1 for u, c in zip(all_user_answers, correct_answers) 
                    if str(u).strip() == str(c).strip().lower())
        total_reward = score * 2

        # 리워드 이력 추가
        supabase.table("reward_history").insert({
            "user_email": email,
            "reward_amount": total_reward,
            "reason": "복습학습을 통한 정답 리워드"
        }).execute()

        # 답변 업데이트 (user_answers JSON 컬럼)
        supabase.table("ocr_data") \
            .update({"user_answers": all_user_answers}) \
            .eq("id", quiz_id) \
            .eq("user_email", email) \
            .execute()
            

        # 유저 포인트 합산 업데이트
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        new_total_points = (user_res.data.get("points") or 0) + total_reward
        supabase.table("users").update({"points": new_total_points}).eq("email", email).execute()

        return {"status": "success", "new_points": new_total_points}
    except Exception as e:
        print(f"오류: {e}")
        return {"status": "error", "message": str(e)}