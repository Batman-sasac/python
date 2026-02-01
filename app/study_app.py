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
    quiz_id: int
    user_answers: List[str]
    correct_answers: List[str]

# 채점 로직
@app.post("/grade")
async def grade_quiz(
    token: str = Form(...),
    email: str = Depends(get_current_user),
    payload: dict = Body(...)
):
    print(f"채점할 유저:{email}")
    
    # 1. 전달받은 데이터 추출 (이름을 payload로 통일)
    correct_ans = payload.get('answer', [])
    user_ans = payload.get('user_answers', [])
    quiz_id = payload.get('quiz_id')

    if not correct_ans or not email:
        return {"status": "error", "message": "필수 데이터가 누락되었습니다."}

    # 채점 로직
    correct_count = 0
    total_questions = len(correct_ans)
    results = []

    for u, c in zip(user_ans, correct_ans):
        is_correct = (str(u).strip() == str(c).strip())
        if is_correct:
            correct_count += 1
        results.append({"user": u, "correct": c, "is_correct": is_correct})

    reward = correct_count
    is_all_correct = (correct_count == total_questions)

    try:
        # [1] 답변 업데이트 (JSONB 자동 처리)
        supabase.table("ocr_data") \
            .update({"user_answers": user_ans}) \
            .eq("id", quiz_id) \
            .eq("user_email", email).execute()

        # [2] 학습 로그 기록
        supabase.table("study_logs").insert({
            "quiz_id": quiz_id, 
            "user_email": email
        }).execute()

        # [3] 리워드 지급 (있을 때만)
        if reward > 0:
            supabase.table("reward_history").insert({
                "user_email": email,
                "reward_amount": reward,
                "reason": f"퀴즈 정답: {correct_count}/{total_questions}"
            }).execute()

            # 포인트 합산 (현재 포인트 조회 후 업데이트)
            user_res = supabase.table("users").select("points").eq("email", email).single().execute()
            new_points = (user_res.data.get("points") or 0) + reward
            supabase.table("users").update({"points": new_points}).eq("email", email).execute()

        return {
            "status": "success",
            "score": correct_count,
            "total": total_questions,
            "reward_given": reward,
            "is_all_correct": is_all_correct,
            "results": results
        }
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return {"status": "error", "message": str(e)}

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

# 복습화면
@app.get("/review_study/{quiz_id}", response_class=HTMLResponse)
async def review_page(
    quiz_id: int,
    token: str = Form(...),
    email: str = Depends(get_current_user)
    ):


    
    print(f"복습화면:{email}")
    print(f"복습 번호:{quiz_id}")

    try:
  # .single()을 사용하여 딕셔너리로 바로 가져옴
        res = supabase.table("ocr_data") \
            .select("id, subject_name, study_name, ocr_text, answers, quiz_html") \
            .eq("id", quiz_id) \
            .eq("user_email", email) \
            .single().execute()
        
        quiz_data = res.data
        
        return templates.TemplateResponse("review_study.html", {
            "request": request,
            "quiz": quiz_data,
            "quiz_json": json.dumps(quiz_data, ensure_ascii=False)
        })
    except Exception:
        return HTMLResponse(content="데이터를 찾을 수 없습니다.", status_code=404)


# 복습 완료 시 리워드 제공 & 사용자 답변 저장 
@app.post("/review-study")
async def review_study_reward(token: str = Form(...),
    email: str = Depends(get_current_user)
    ):
    print(f"복습 완료 시 리워드 제공 유저:{email}")
    
    data = await request.json()
    quiz_id = data.get("quiz_id")
    all_user_answers = data.get("user_answers")

    try:
        # DB에서 정답 가져오기
        res = supabase.table("ocr_data").select("answers").eq("id", quiz_id).single().execute()
        correct_answers = res.data.get("answers", [])

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

        # 답변 업데이트
        supabase.table("ocr_data") \
            .update({"user_answers": all_user_answers}) \
            .eq("id", quiz_id).execute()

        # 유저 포인트 합산 업데이트
        user_res = supabase.table("users").select("points").eq("email", email).single().execute()
        new_total_points = (user_res.data.get("points") or 0) + total_reward
        supabase.table("users").update({"points": new_total_points}).eq("email", email).execute()

        return {"status": "success", "new_points": new_total_points}
    except Exception as e:
        print(f"오류: {e}")
        return {"status": "error", "message": str(e)}