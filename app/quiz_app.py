from fastapi import APIRouter, HTTPException, Cookie, Body, Request, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
from datetime import datetime, timedelta

app = APIRouter(prefix="/quiz", tags=["Quiz"])


# 퀴즈 제출 모델 (사용자가 푼 답안)
class QuizSubmitRequest(BaseModel):
    quiz_id: int  # DB 연동 전이라면 테스트용으로 일단 둡니다
    user_answers: List[str]
    correct_answers: List[str]  # 검증을 위해 프론트에서 같이 보내거나 DB에서 가져옴

@app.post("/grade")
async def grade_quiz(
    payload: dict = Body(...),
    user_email: Optional[str] = Cookie(None)
):
    if not correct_ans:
        return {"error": "데이터가 필요합니다."}

    # 1. 채점 로직
    score = 0
    correct_count = 0
    total_questions = len(correct_ans)
    results = []

    for u, c in zip(user_ans, correct_ans):
        is_correct = (u.strip() == c.strip())
        if is_correct:
            score += 1
            correct_count += 1
        results.append({"user": u, "correct": c, "is_correct": is_correct})

    # 2. 리워드 계산 (보내주신 로직 반영)
    reward = score  # 기본적으로 맞춘 개수당 1점
    is_all_correct = (correct_count == total_questions)
    
    if is_all_correct and total_questions > 0:
        reward = 30  # 다 맞추면 보너스로 30점

    # 3. DB에 리워드 저장 (연결된 이메일 기준)
    conn = get_db()
    cur = conn.cursor()
    try:
        if reward > 0:
            cur.execute("""
                INSERT INTO reward_history (user_email, reward_amount, reason) 
                VALUES (%s, %s, %s)
            """, (user_email, reward, f"퀴즈 결과: {correct_count}/{total_questions} 정답"))
            
            cur.execute("""
            UPDATE users 
            SET point = point + %s 
            WHERE email = %s
            """, (reward, user_email))
            
            conn.commit()

            # 4. 결과 출력 (터미널 로그)
        print("\n" + "🎯"*10 + " 채점 결과 " + "🎯"*10)
        print(f"정답률: {correct_count}/{total_questions}")
        print(f"획득 점수: {score}점")
        print(f"최종 리워드: {reward}P {'(2배 보너스!)' if is_all_correct else ''}")
        print(f"상세 결과: {results}")
        print("="*40 + "\n")

        return {
            "score": score,
            "total": total_questions,
            "reward_given": reward,
            "is_all_correct": is_all_correct,
            "results": results
        }
    except Exception as e:
        print(f"리워드 저장 오류: {e}")
        return {"error": "채점은 완료되었으나 리워드 저장에 실패했습니다."}
    finally:
        cur.close()
        conn.close()
