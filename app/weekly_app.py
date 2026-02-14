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


# 1. 학습 목표 설정 (UPDATE)
@app.post("/set-goal")
async def set_study_goal(token: str = Form(...),
email: str = Depends(get_current_user),
cycle_count: int = Form(...)   # 학습 목표 횟수
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

        

# 2. 주간 성장 그래프 데이터 (SELECT & 가공)
@app.get("/stats/weekly-growth")
async def get_weekly_growth(
email: str = Depends(get_current_user)
):

    print(f"주간 성장 데이터 유저:{email}")
 
    try:
        # 5주 전 월요일부터의 데이터를 가져옴
        five_weeks_ago = (date.today() - timedelta(weeks=5)).isoformat()
        
        # 1. 원본 데이터 가져오기 (CTE 대신 파이썬에서 그룹화)
        res = supabase.table("ocr_data") \
            .select("id, created_at") \
            .eq("user_email", email) \
            .gte("created_at", five_weeks_ago) \
            .execute()

        data = res.data
        
        # 2. 주차별 그룹화 및 점수 계산 (파이썬 로직)
        weekly_map = {}
        for item in data:
            dt = datetime.fromisoformat(item['created_at'].replace('Z', '+00:00'))
            # 해당 주차의 월요일 구하기
            week_start = (dt.date() - timedelta(days=dt.weekday())).isoformat()
            
            if week_start not in weekly_map:
                weekly_map[week_start] = {"attend_dates": set(), "count": 0}
            
            weekly_map[week_start]["attend_dates"].add(dt.date())
            weekly_map[week_start]["count"] += 1

        # 3. 라벨 및 점수 생성 (최근 5주)
        labels = []
        scores = []
        today_monday = date.today() - timedelta(days=date.today().weekday())

        for i in range(4, -1, -1):
            target_date = (today_monday - timedelta(weeks=i))
            target_iso = target_date.isoformat()
            
            # 라벨 이름 정하기
            if i == 0: label = "이번 주"
            elif i == 1: label = "지난 주"
            else: label = f"{i}주 전"
            
            labels.append(label)
            
            # 점수 계산
            stats = weekly_map.get(target_iso)
            if stats:
                attend_days = len(stats["attend_dates"])
                activity_score = stats["count"] * 10.0
                growth_score = min((activity_score * (attend_days / 7.0)), 100)
                scores.append(round(growth_score, 1))
            else:
                scores.append(0)

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