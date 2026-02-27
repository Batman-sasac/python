# 재첨 후 정답 저장

import asyncio
from fastapi import APIRouter, HTTPException, Body, Depends, Form
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from core.database import supabase
import json
import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.security_app import get_current_user

app = APIRouter(prefix="/study", tags=["study"])
templates = Jinja2Templates(directory="templates")

# 퀴즈 제출 모델 — 프론트 GradeStudyRequest와 동일 (JSON body)
class QuizSubmitRequest(BaseModel):
    quiz_id: int
    user_answers: List[str]
    correct_answers: List[str]
    grade_cnt: int
    original_text: List[str] = []
    keywords: List[str] = []
    quiz_html: str = ""
    ocr_text: Optional[Dict[str, Any]] = None  # { pages, blanks, quiz } 또는 생략
    subject_name: Optional[str] = None
    study_name: Optional[str] = None



# 채점 — 프론트: POST /study/grade, JSON body (QuizSubmitRequest) → { status, score, reward_given, new_points }
@app.post("/grade")
async def grade_quiz(
    email: str = Depends(get_current_user),
    payload: QuizSubmitRequest = Body(...)
):
    print(f"채점할 유저:{email}")
    
    # 1. 전달받은 데이터 추출
    quiz_id = payload.quiz_id
    user_ans = payload.user_answers
    correct_ans = payload.correct_answers
    grade_cnt = payload.grade_cnt
    quiz_html = payload.quiz_html

    # ocr_data.ocr_text: 프론트에서 보내면 그대로, 없으면 original_text/keywords로 구성
    ocr_text = payload.ocr_text
    if ocr_text is None:
        ocr_text = {
            "pages": [{"original_text": "\n".join(payload.original_text), "keywords": payload.keywords}],
            "blanks": [{"blank_index": i, "word": w, "page_index": 0} for i, w in enumerate(payload.keywords)],
            "quiz": {"raw": payload.quiz_html or ""},
        }

    if not correct_ans or not email:
        return {"status": "error", "message": "필수 데이터가 누락되었습니다."}

    try:
        # [1] OCR 데이터 저장 (id는 DB 자동 생성)
        row = {
            "user_email": email,
            "subject_name": payload.subject_name or "학습 자료",
            "study_name": payload.study_name or payload.subject_name or "학습 자료",
            "user_answers": user_ans,
            "answers": correct_ans,
            "ocr_text": ocr_text,
            "quiz_html": {"raw": quiz_html} if isinstance(quiz_html, str) else quiz_html,
        }
        insert_res = supabase.table("ocr_data").insert(row).execute()
        new_id = insert_res.data[0]["id"] if insert_res.data else None

        # RLS 등으로 insert 반환값이 비어 있으면, 방금 넣은 행을 조회해서 id 사용
        if new_id is None:
            fallback = (
                supabase.table("ocr_data")
                .select("id")
                .eq("user_email", email)
                .order("id", desc=True)
                .limit(1)
                .execute()
            )
            if fallback.data and len(fallback.data) > 0:
                new_id = fallback.data[0]["id"]

        # [2] 학습 로그 + [3] 리워드: 서로 독립이므로 병렬 실행 (DB 왕복 횟수 감소)
        new_points = None
        if new_id is not None:
            if grade_cnt > 0:
                reward_amount = grade_cnt * 2
                print(f"reward_amount: {reward_amount}")
                await asyncio.gather(
                    asyncio.to_thread(
                        lambda: supabase.table("study_logs").insert({
                            "quiz_id": new_id,
                            "user_email": email,
                            "completed_at": datetime.now().isoformat(),
                        }).execute()
                    ),
                    asyncio.to_thread(
                        lambda: supabase.table("reward_history").insert({
                            "user_email": email,
                            "reward_amount": reward_amount,
                            "reason": f"초기 학습 리워드: {grade_cnt}개 정답"
                        }).execute()
                    ),
                )
                # 포인트 조회·업데이트는 리워드 insert 이후에만 의미 있음
                user_res = await asyncio.to_thread(
                    lambda: supabase.table("users")
                    .select("points")
                    .eq("email", email)
                    .single()
                    .execute()
                )
                current_points = user_res.data.get("points") or 0
                new_points = current_points + reward_amount
                await asyncio.to_thread(
                    lambda: supabase.table("users")
                    .update({"points": new_points})
                    .eq("email", email)
                    .execute()
                )
            else:
                await asyncio.to_thread(
                    lambda: supabase.table("study_logs").insert({
                        "quiz_id": new_id,
                        "user_email": email,
                        "completed_at": datetime.now().isoformat(),
                    }).execute()
                )

        return {
            "status": "success",
            "score": grade_cnt,
            "reward_given": grade_cnt * 2 if grade_cnt > 0 else 0,
            "new_points": new_points
        }

    except Exception as e:
        print(f"오류: {e}")
        return {"status": "error", "message": str(e)}

# 복습화면
@app.get("/review_study/{quiz_id}", response_class=HTMLResponse)
async def review_page(
    request: Request,
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


# 복습 완료 — 프론트: POST /study/review-study, JSON { quiz_id, user_answers[] } → { status, new_points }
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

        # 리워드 이력 / ocr_data 업데이트 / study_logs — 서로 독립이므로 병렬 실행
        await asyncio.gather(
            asyncio.to_thread(
                lambda: supabase.table("reward_history").insert({
                    "user_email": email,
                    "reward_amount": total_reward,
                    "reason": "복습학습을 통한 정답 리워드"
                }).execute()
            ),
            asyncio.to_thread(
                lambda: supabase.table("ocr_data")
                .update({"user_answers": all_user_answers})
                .eq("id", quiz_id)
                .eq("user_email", email)
                .execute()
            ),
            asyncio.to_thread(
                lambda: supabase.table("study_logs").insert({
                    "user_email": email,
                    "quiz_id": quiz_id,
                    "completed_at": datetime.now().isoformat()
                }).execute()
            ),
        )

        # 유저 포인트 합산 업데이트 (리워드 반영 후 1회 조회 + 1회 업데이트)
        user_res = await asyncio.to_thread(
            lambda: supabase.table("users").select("points").eq("email", email).single().execute()
        )
        new_total_points = (user_res.data.get("points") or 0) + total_reward
        await asyncio.to_thread(
            lambda: supabase.table("users").update({"points": new_total_points}).eq("email", email).execute()
        )

        return {"status": "success", "new_points": new_total_points}
    except Exception as e:
        print(f"오류: {e}")
        return {"status": "error", "message": str(e)}