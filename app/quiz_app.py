from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

app = APIRouter(prefix="/quiz", tags=["Quiz"])


# 퀴즈 제출 모델 (사용자가 푼 답안)
class QuizSubmitRequest(BaseModel):
    quiz_id: int  # DB 연동 전이라면 테스트용으로 일단 둡니다
    user_answers: List[str]
    correct_answers: List[str]  # 검증을 위해 프론트에서 같이 보내거나 DB에서 가져옴

@app.post("/grade")
async def grade_quiz(submission: QuizSubmitRequest):
    user_ans = submission.user_answers
    correct_ans = submission.correct_answers
    
    # 1. 개수 확인
    if len(user_ans) != len(correct_ans):
        raise HTTPException(status_code=400, detail="답안의 개수가 일치하지 않습니다.")

    # 2. 채점 로직
    score = 0
    correct_count = 0
    total_questions = len(correct_ans)
    
    results = [] # 각 문제당 정오표
    for u, c in zip(user_ans, correct_ans):
        is_correct = (u.strip() == c.strip())
        if is_correct:
            score += 1
            correct_count += 1
        results.append({"user": u, "correct": c, "is_correct": is_correct})

    reward = score
    is_all_correct = (correct_count == total_questions)
    
    if is_all_correct:
        reward = score * 2

    # 4. 결과 출력 (터미널 로그)
    print("\n" + "🎯"*10 + " 채점 결과 " + "🎯"*10)
    print(f"정답률: {correct_count}/{total_questions}")
    print(f"획득 점수: {score}점")
    print(f"최종 리워드: {reward}P {'(2배 보너스!)' if is_all_correct else ''}")
    print(f"상세 결과: {results}")
    print("="*40 + "\n")

    return {
        "status": "success",
        "score": score,
        "reward": reward,
        "is_all_correct": is_all_correct,
        "details": results
    }
