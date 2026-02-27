# 학습 주기 세팅 및 주마다의 그래프 도출 

from fastapi import APIRouter, Body, HTTPException, Depends, Form
from typing import Optional
from fastapi.responses import HTMLResponse
import psycopg2
import os
from core.database import supabase
from flask import Flask, request, jsonify
from datetime import datetime, date, timedelta
import calendar

from app.security_app import get_current_user

app = APIRouter(prefix="/cycle", tags=["Weekly"])


# 1. 학습 목표 설정 (UPDATE) — 프론트: POST Form cycle_count (필수). token은 선택(Bearer만 써도 됨)
@app.post("/set-goal")
async def set_study_goal(
    email: str = Depends(get_current_user),
    cycle_count: int = Form(...),  # 학습 목표 횟수 (필수)
    token: Optional[str] = Form(None),  # 호환용, 없으면 Authorization Bearer 사용
):

    print(f"학습 목표 횟수: {cycle_count}")

    if not cycle_count or int(cycle_count) < 1:
        return {"status": "error", "message": "올바른 목표 횟수를 입력하세요."}

    try:
        # SDK 버전 업데이트
        supabase.table("users") \
            .update({"monthly_goal": int(cycle_count)}) \
            .eq("email", email).execute()
        
        return {
            "status": "success", 
            "target_count": cycle_count,
            "message": "목표가 성공적으로 저장되었습니다."
        }
    except Exception as e:
        return {"status": "error", "message": f"DB 저장 실패: {str(e)}"}

        

# 2. 주간 성장 그래프: (해당 주 정답률) * (해당 주 출석률)
# 정답률 = (해당 주 전체 정답 수 / 해당 주 전체 문항 수) * 100
# 출석률 = (실제 출석 일수 / 7일) * 100
# 주차 점수 = (정답률 * 출석률) / 100 → 0~100
@app.get("/stats/weekly-growth")
async def get_weekly_growth(
    email: str = Depends(get_current_user)
):
    print(f"주간 성장 데이터 유저:{email}")

    try:
        five_weeks_ago = (date.today() - timedelta(weeks=5)).isoformat()

        # 1) study_logs: 학습지별 정답 수·문항 수 (DB 저장값 사용)
        logs_res = supabase.table("study_logs") \
            .select("completed_at, correct_count, question_count") \
            .eq("user_email", email) \
            .gte("completed_at", five_weeks_ago) \
            .execute()
        logs = logs_res.data or []

        # 2) reward_history: 출석체크만으로 해당 주 실제 출석 일수
        reward_res = supabase.table("reward_history") \
            .select("created_at, reason") \
            .eq("user_email", email) \
            .eq("reason", "출석체크") \
            .gte("created_at", five_weeks_ago) \
            .execute()
        rewards = reward_res.data or []

        def _week_start(d):
            if isinstance(d, str):
                d = datetime.fromisoformat(d.replace("Z", "+00:00")).date()
            return (d - timedelta(days=d.weekday())).isoformat()

        # 주차별: 전체 정답 수 합계, 전체 문항 수 합계, 출석한 날 집합
        weekly = {}
        for row in logs:
            completed = row.get("completed_at")
            if not completed:
                continue
            week_key = _week_start(completed)
            if week_key not in weekly:
                weekly[week_key] = {"correct_sum": 0, "question_sum": 0, "attend_dates": set()}
            weekly[week_key]["correct_sum"] += row.get("correct_count") or 0
            weekly[week_key]["question_sum"] += row.get("question_count") or 0

        for row in rewards:
            created = row.get("created_at")
            if not created:
                continue
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            week_key = _week_start(dt.date())
            if week_key not in weekly:
                weekly[week_key] = {"correct_sum": 0, "question_sum": 0, "attend_dates": set()}
            weekly[week_key]["attend_dates"].add(dt.date())

        # 3) 라벨 및 점수: 정답률(%) * 출석률(%) / 100
        labels = []
        scores = []
        today_monday = date.today() - timedelta(days=date.today().weekday())

        for i in range(4, -1, -1):
            target_monday = today_monday - timedelta(weeks=i)
            target_iso = target_monday.isoformat()
            if i == 0:
                label = "이번 주"
            elif i == 1:
                label = "지난 주"
            else:
                label = f"{i}주 전"
            labels.append(label)

            st = weekly.get(target_iso)
            if not st:
                scores.append(0)
                continue
            question_sum = st["question_sum"]
            correct_sum = st["correct_sum"]
            # 정답률 = (해당 주 전체 정답 수 / 해당 주 전체 문항 수) * 100
            correct_rate = (correct_sum / question_sum * 100.0) if question_sum > 0 else 0.0
            # 출석률 = (실제 출석 일수 / 7일) * 100
            attend_days = len(st["attend_dates"])
            attendance_rate = min(attend_days / 7.0, 1.0) * 100.0
            # 주차 점수 = (정답률 * 출석률) / 100 → 0~100
            score = (correct_rate * attendance_rate) / 100.0
            scores.append(round(score, 1))

        return {"labels": labels, "data": scores}
    except Exception as e:
        return {"error": str(e)}

# 3. 학습 통계 비교 이번 달 vs 목표 횟수
@app.get("/learning-stats")
async def get_learning_stats(
email: str = Depends(get_current_user)
):
    
    today = date.today()
    this_month_start = today.replace(day=1).isoformat()

    try:
        # 1. 이번 달 기록 조회
        this_res = supabase.table("study_logs") \
            .select("id", count="exact") \
            .eq("user_email", email) \
            .gte("completed_at", this_month_start).execute()
        this_month_count = this_res.count


        # 3. 목표 횟수 조회
        user_res = supabase.table("users").select("target_count").eq("email", email).single().execute()
        target_count = user_res.data.get("target_count") if user_res.data else 0

        return {
            "status": "success",
            "compare": {
                "this_month_name": f"{today.month}월",
                "this_month_count": this_month_count,
                "target_count": target_count,
                "diff": target_count - this_month_count
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}