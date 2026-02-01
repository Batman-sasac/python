from fastapi import APIRouter, Depends, Form
from database import supabase
from datetime import date
from typing import Optional

from app.security.security_app import get_current_user


app = APIRouter(tags=["Reward"])

# 출석체크 리워드 제공 로직
async def check_attendance_and_reward(token: str = Form(...),
email: str = Depends(get_current_user)):

    print(f"출석제크 리워드 유저:{email}")
    
    today = date.today()

    try:
        # 1. 중복 확인
        check_res = supabase.table("reward_history") \
            .select("id") \
            .eq("user_email", email) \
            .eq("reason", "출석체크") \
            .gte("created_at", f"{today}T00:00:00") \
            .lt("created_at", f"{today}T23:59:59") \
            .execute()
        
        # 이미 데이터가 존재한다면 현재 포인트만 조회해서 반환
        if check_res.data:
            user_res = supabase.table("users").select("points").eq("email", email).single().execute()
            current_pt = user_res.data.get("points", 0)
            return False, current_pt

        # 2. 리워드 이력 추가 (INSERT)
        supabase.table("reward_history").insert({
            "user_email": email,
            "reward_amount": 10,
            "reason": "출석체크"
        }).execute()

        # 3. 유저 포인트 업데이트 (UPDATE)
        # 먼저 현재 포인트를 가져와서 +10 (기존 코드에서는 +1이었으나 맥락상 10P 지급으로 수정)
        user_data_res = supabase.table("users").select("points").eq("email", email).single().execute()
        current_points = user_data_res.data.get("points", 0)
        new_total_points = current_points + 10

        update_res = supabase.table("users") \
            .update({"points": new_total_points}) \
            .eq("email", email) \
            .execute()

        print(f"🎊 [리워드 지급] {email}: 10P 완료 (총: {new_total_points}P)")
        return True, new_total_points

    except Exception as e:
        print(f"❌ 리워드 지급 중 오류 발생: {e}")
        return False, 0