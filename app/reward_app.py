from fastapi import APIRouter, Cookie
from database import get_db
from datetime import date
from typing import Optional


app = APIRouter(tags=["Reward"])

async def check_attendance_and_reward(user_email: str):
    if not user_email: return False, 0
    
    conn = get_db()
    cur = conn.cursor()
    today = date.today()

    try:
        # 1. 중복 확인
        cur.execute("SELECT id FROM reward_history WHERE user_email = %s AND reason = '출석체크' AND DATE(created_at) = %s", (user_email, today))
        
        if cur.fetchone():
            # 이미 받은 경우, 현재 포인트만 조회해서 반환
            cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))
            current_pt = cur.fetchone()[0]
            return False, current_pt

        # 2. 리워드 지급 및 포인트 합산
        cur.execute("INSERT INTO reward_history (user_email, reward_amount, reason) VALUES (%s, 1, '출석체크')", (user_email,))
        
        # ⚠️ 주의: DB 컬럼명이 point인지 points인지 꼭 확인하세요!
        cur.execute("UPDATE users SET points = points + 1 WHERE email = %s", (user_email,))
        
        # 3. 업데이트 된 최종 포인트 조회
        cur.execute("SELECT points FROM users WHERE email = %s", (user_email,))
        new_total_points = cur.fetchone()[0]

        conn.commit()
        print(f"🎊 [리워드 지급] {user_email}: 1P 완료 (총: {new_total_points}P)")
        return True, new_total_points # 성공 여부와 포인트를 함께 반환

    except Exception as e:
        conn.rollback()
        print(f"❌ 오류: {e}")
        return False, 0
    finally:
        cur.close()
        conn.close()

# 출석률*정답률에 따른 그래프 도출을 위한 데이터 
@app.get("/stats/weekly-growth")
async def get_weekly_growth(user_email: str = Cookie(None)):
    if not user_email:
        return {"error": "로그인이 필요합니다."}

    conn = get_db()
    cur = conn.cursor()
    
    try:
        # 주별 정답률과 출석률을 곱해서 성장 점수(growth_score) 도출
        cur.execute("""
            SELECT 
                quiz.week_start,
                (quiz.avg_correct_rate * COALESCE(att.att_rate, 0)) * 100 AS growth_score
            FROM (
                SELECT 
                    DATE_TRUNC('week', created_at) as week_start,
                    SUM(correct_count)::float / NULLIF(SUM(total_count), 0) as avg_correct_rate
                FROM quiz_results
                WHERE user_email = %s
                GROUP BY 1
            ) quiz
            LEFT JOIN (
                SELECT 
                    DATE_TRUNC('week', created_at) as week_start,
                    COUNT(DISTINCT DATE(created_at)) / 7.0 as att_rate
                FROM reward_history
                WHERE user_email = %s AND reason = '출석체크'
                GROUP BY 1
            ) att ON quiz.week_start = att.week_start
            ORDER BY quiz.week_start DESC
            LIMIT 5;
        """, (user_email, user_email))
        
        rows = cur.fetchall()
        
        # 그래프용 데이터 포맷팅
        labels = [row[0].strftime("%m/%d") for row in reversed(rows)]
        values = [round(row[1], 1) for row in reversed(rows)]
        
        return {
            "labels": ["이번 주", "1주 전", "2주 전", "3주 전", "4주 전"],
            "datasets": scores  # 이 부분이 바로 그래프를 그리는 '숫자들'입니다.
        }
    finally:
        cur.close()
        conn.close()