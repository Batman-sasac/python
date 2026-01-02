# 재첨 후 정답 저장 

from fastapi import APIRouter, HTTPException, Cookie, Body, Request
from pydantic import BaseModel
from typing import List, Optional
from database import get_db
import json

app = APIRouter(prefix="/quiz", tags=["Quiz"])

# 퀴즈 제출 모델
class QuizSubmitRequest(BaseModel):
    quiz_id: int
    user_answers: List[str]
    correct_answers: List[str]

@app.post("/grade")
async def grade_quiz(
    payload: dict = Body(...),
    user_email: Optional[str] = Cookie(None)
):
    # 1. 전달받은 데이터 추출 (이름을 payload로 통일)
    correct_ans = payload.get('correct_answers', [])
    user_ans = payload.get('user_answers', [])
    quiz_id = payload.get('quiz_id')

    if not correct_ans:
        return {"status": "error", "message": "정답 데이터가 없습니다."}
    
    if not user_email:
        return {"status": "error", "message": "로그인이 필요합니다."}

    # 2. 채점 로직
    score = 0
    correct_count = 0
    total_questions = len(correct_ans)
    results = []

    for u, c in zip(user_ans, correct_ans):
        # 공백 제거 후 비교
        is_correct = (str(u).strip() == str(c).strip())
        if is_correct:
            correct_count += 1
        results.append({"user": u, "correct": c, "is_correct": is_correct})

    score = correct_count # 맞춘 개수
    
    # 3. 리워드 계산
    reward = score  # 기본 1점씩
    is_all_correct = (correct_count == total_questions and total_questions > 0)
    
    if is_all_correct:
        reward = 30  # 다 맞추면 보너스 포함 30점

    # 4. DB 저장
    conn = get_db()
    cur = conn.cursor()
    try:
        # 리워드 내역 저장
        if reward > 0:
            cur.execute("""
                INSERT INTO reward_history (user_email, reward_amount, reason) 
                VALUES (%s, %s, %s)
            """, (user_email, reward, f"퀴즈 정답: {correct_count}/{total_questions}"))
            
            # 사용자 포인트 업데이트
            cur.execute("""
                UPDATE users 
                SET points = points + %s 
                WHERE email = %s
            """, (reward, user_email))

        # 사용자가 입력한 답안 업데이트 (ocr_data 테이블)
        # 리스트 형태이므로 json.dumps로 문자열화하여 저장하는 것이 안전합니다.
        cur.execute("""
            UPDATE ocr_data 
            SET answers = %s 
            WHERE id = %s AND user_email = %s
        """, (user_ans, quiz_id, user_email))

        conn.commit()

        # 터미널 로그 출력
        print("\n" + "🎯"*10 + " 채점 결과 " + "🎯"*10)
        print(f"사용자: {user_email}")
        print(f"정답률: {correct_count}/{total_questions}")
        print(f"최종 리워드: {reward}P {'(올백 보너스!)' if is_all_correct else ''}")
        print("="*40 + "\n")

        return {
            "status": "success",
            "score": correct_count,
            "total": total_questions,
            "reward_given": reward,
            "is_all_correct": is_all_correct,
            "results": results
        }
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ 리워드 저장 오류: {e}")
        return {"status": "error", "message": f"리워드 저장 실패: {str(e)}"}
    finally:
        cur.close()
        conn.close()