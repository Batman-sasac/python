import os
from dotenv import load_dotenv
import requests
import psycopg2
from fastapi import APIRouter, Response, Request, Header, Form, Depends
from fastapi.responses import RedirectResponse
from typing import Optional
from dotenv import load_dotenv
from core.database import supabase
from pydantic import BaseModel
from app.security_app import create_jwt_token, get_current_user
import jwt
from datetime import datetime, timedelta, date
from fastapi.responses import JSONResponse
from fastapi import Form



load_dotenv()
app = APIRouter(prefix="/auth", tags=["Auth"])


class NicknameUpdate(BaseModel): # 프론트에 맞춰 Form이 아닌 data로
    nickname: str
    email: Optional[str] = None
    social_id: Optional[str] = None


# --- [2. 닉네임 설정 API] ---
@app.post("/set-nickname") 
async def set_nickname_mobile(
    data: NicknameUpdate,
    email: str = Depends(get_current_user)
):
    try:
        nickname = data.nickname
        print(f"토큰 주인 이메일: {email}, 설정하려는 닉네임: {nickname}")

        # 1. social_id 조회 (토큰 생성용)
        user_res = supabase.table("users").select("social_id").eq("email", email).execute()
        social_id = None
        if user_res.data and len(user_res.data) > 0:
            social_id = user_res.data[0].get("social_id") or data.social_id
        if not social_id and data.social_id:
            social_id = data.social_id

        # 2. 닉네임 업데이트 (서버 DB에 저장)
        update_res = supabase.table("users") \
            .update({"nickname": nickname}) \
            .eq("email", email) \
            .execute()

        if not update_res.data:
            return JSONResponse(status_code=404, content={"error": "사용자를 찾을 수 없습니다."})

        # 3. 새 JWT 발급 (프론트엔드가 저장할 수 있도록)
        social_id_str = str(social_id) if social_id else (data.social_id or "unknown")
        token = create_jwt_token(email, social_id_str)

        return {
            "status": "success",
            "token": token,
            "nickname": nickname,
            "email": email,
            "message": "닉네임이 설정되었습니다."
        }
    except Exception as e:
        print(f"닉네임 설정 오류: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


# --- [3. 사용자 학습 통계 (총 학습 횟수, 연속 학습일, 한달 목표)] ---
@app.get("/user/stats")
async def get_user_stats(email: str = Depends(get_current_user)):
    """총 학습 횟수, 총 학습일, 연속 학습일, 한달 목표 반환 (study_logs.completed_at 기준)"""
    try:
        today = date.today()

        # 1. 총 학습 횟수: study_logs 전체 건수
        total_res = supabase.table("study_logs") \
            .select("id", count="exact") \
            .eq("user_email", email) \
            .execute()
        total_learning_count = getattr(total_res, "count", None)
        if total_learning_count is None and total_res.data is not None:
            total_learning_count = len(total_res.data)
        if total_learning_count is None:
            total_learning_count = 0

        # 2. 총 학습일·연속 학습일: study_logs.completed_at 기준 distinct 날짜 계산
        logs_res = supabase.table("study_logs") \
            .select("completed_at") \
            .eq("user_email", email) \
            .execute()
        study_dates = set()
        for row in (logs_res.data or []):
            completed = row.get("completed_at")
            if completed:
                if isinstance(completed, str):
                    study_dates.add(completed[:10])  # YYYY-MM-DD
                else:
                    study_dates.add(str(completed)[:10])
        consecutive_days = 0  # 연속 학습일: 오늘부터 역순으로 연속된 일수
        check = today
        check_str = check.isoformat()
        while check_str in study_dates:
            consecutive_days += 1
            check -= timedelta(days=1)
            check_str = check.isoformat()

        # 3. 한달 목표: users.target_count
        user_res = supabase.table("users") \
            .select("monthly_goal") \
            .eq("email", email) \
            .single() \
            .execute()
        monthly_goal = 0
        if user_res.data and user_res.data.get("monthly_goal") is not None:
            monthly_goal = int(user_res.data["monthly_goal"])

        return {
            "status": "success",
            "data": {
                "total_learning_count": total_learning_count,
                "consecutive_days": consecutive_days,
                "monthly_goal": monthly_goal,
            }
        }
    except Exception as e:
        print(f"사용자 통계 조회 오류: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


    

