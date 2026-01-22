# 학습 주기 세팅 및 주마다의 그래프 도출 

from fastapi import APIRouter, Cookie, Body, HTTPException
from typing import Optional
from fastapi.responses import HTMLResponse
import psycopg2
import os
from database import get_db
from flask import Flask, request, jsonify
from datetime import datetime, date, timedelta
import calendar

app = APIRouter(prefix="/cycle", tags=["Weekly"])


@app.post("/set-goal")
async def set_study_goal(
    payload: dict = Body(...), 
    request : Request
):

    user_email = request.state.user_email
    
    cycle_count = payload.get("cycle_count")
    if not cycle_count or int(cycle_count) < 1:
        return {"status": "error", "message": "올바른 목표 횟수를 입력하세요."}

    conn = get_db()
    cur = conn.cursor()
    try:
        # 기존 목표가 있는지 확인 후 업데이트 또는 삽입 (UPSERT 로직)
        cur.execute("""
            UPDATE users SET target_count = %s 
            where email = %s
        """, (int(cycle_count), user_email))
        
        
        conn.commit()
        return {
            "status": "success", 
            "target_count": cycle_count,
            "message": "목표가 성공적으로 저장되었습니다." # message를 추가해주면 더 안전합니다.
        }
    except Exception as e:
        if conn: conn.rollback()
        print(f"❌ 서버 내부 에러: {str(e)}") # 서버 터미널 로그를 확인하세요!
        # 여기서 message를 정확히 내려줘야 프론트에서 undefined가 안 뜹니다.
        return {"status": "error", "message": f"DB 저장 실패: {str(e)}"}
    finally:
        if conn:
            cur.close()
            conn.close()


@app.get("/setting", response_class=HTMLResponse)
async def index_page(request: Request): 
    user_email = request.state.user_email
    print(f"현재 브라우저에서 넘어온 쿠키 값: {user_email}") # 서버 터미널에 출력됨
    
    with open("templates/weeklyTarget.html", "r", encoding="utf-8") as f:
        return f.read()


# 출석률*정답률에 따른 그래프 도출을 위한 데이터 
@app.get("/stats/weekly-growth")
async def get_weekly_growth(request: Request):

    user_email = request.state.user_email

    if not user_email:
        return {"error": "로그인이 필요합니다."}

    conn = get_db()
    cur = conn.cursor()
    
    try:
        # ocr_data를 기준으로 주간 성장 점수 도출
        # (노트 생성일 = 출석일 / 정답률 = 임시로 100% 또는 생성 빈칸 수 비례 설정 가능)
        cur.execute("""
            WITH weekly_stats AS (
                SELECT 
                    DATE_TRUNC('week', created_at)::date as week_start,
                    COUNT(DISTINCT DATE(created_at)) as attend_days,
                    -- 실제 채점 데이터가 없을 경우, 문제를 생성한 성실도를 점수로 환산 (예: 생성 개수 비례)
                    COUNT(id) * 10.0 as activity_score 
                FROM ocr_data
                WHERE user_email = %s
                GROUP BY 1
            )
            SELECT 
                week_start,
                -- (활동 점수 * 출석률(attend_days/7)) 형식으로 점수화
                LEAST((activity_score * (attend_days / 7.0)), 100) as growth_score
            FROM weekly_stats
            ORDER BY week_start DESC
            LIMIT 5;
        """, (user_email,))
        
        rows = cur.fetchall()
        
        # 최신 데이터가 오른쪽으로 가도록 뒤집기
        rows_reversed = list(reversed(rows))
        
        # 그래프용 라벨 및 데이터 생성
        labels = []
        scores = []
        
        for i, row in enumerate(rows_reversed):
            # 주차별 라벨 생성
            diff = len(rows_reversed) - 1 - i
            if diff == 0:
                label = "이번 주"
            elif diff == 1:
                label = "지난 주"
            else:
                label = f"{diff}주 전"
            
            labels.append(label)
            scores.append(round(row[1], 1))

        # 데이터가 5개보다 적을 경우를 대비해 기본값 채우기 (선택사항)
        while len(labels) < 5:
            labels.insert(0, f"{len(labels)+1}주 전")
            scores.insert(0, 0)

        return {
            "labels": labels,
            "data": scores  # 프론트엔드 Chart.js에서 사용하기 쉬운 이름
        }
    except Exception as e:
        print(f"그래프 데이터 도출 오류: {e}")
        return {"error": str(e)}
    finally:
        cur.close()
        conn.close()



@app.get("/learning-stats")
async def get_learning_stats(request: Request):

    user_email = request.state.user_email

    if not user_email:
        return {"status": "error", "message": "로그인이 필요합니다."}

    # 1. 날짜 계산
    today = date.today() # 예: 2026-01-13
    
    # 이번 달 시작일: 2026-01-01
    this_month_start = today.replace(day=1)
    
    # 지난 달 마지막 날: 2025-12-31 (timedelta(days=1)이 연도까지 알아서 바꿔줌)
    last_month_end = this_month_start - timedelta(days=1)
    
    # 지난 달 시작일: 2025-12-01
    last_month_start = last_month_end.replace(day=1)
    
    conn = get_db()
    cur = conn.cursor()
    try:
        # 2. 이번 달 횟수 (>= 2026-01-01)
        cur.execute("""
            SELECT COUNT(*) FROM study_logs 
            WHERE user_email = %s AND completed_at >= %s
        """, (user_email, this_month_start))
        this_month_count = cur.fetchone()[0]

        # 3. 지난 달 횟수 (2025-12-01 <= data < 2026-01-01)
        # BETWEEN 대신 < 를 사용하면 지난달 마지막날 밤 데이터까지 안전하게 포함됩니다.
        cur.execute("""
            SELECT COUNT(*) FROM study_logs 
            WHERE user_email = %s AND completed_at >= %s AND completed_at < %s
        """, (user_email, last_month_start, this_month_start))
        last_month_count = cur.fetchone()[0]

        # 4. 목표 횟수 가져오기 (users 테이블)
        cur.execute("SELECT target_count FROM users WHERE email = %s", (user_email, ))
        row = cur.fetchone()
        target_count = row[0] if row and row[0] is not None else 0

        return {
            "status": "success",
            "compare": {
                "last_month_name": last_month_start.strftime('%m월'), # '12월'
                "last_month_count": last_month_count,
                "this_month_name": this_month_start.strftime('%m월'), # '01월'
                "this_month_count": this_month_count,
                "target_count": target_count,
                "diff": this_month_count - last_month_count
            }
        }
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        cur.close()
        conn.close()