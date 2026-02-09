# 신고 접수 API
# reports 테이블 컬럼: reporter_email, report_type, content, target_type, target_id, created_at, status

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.security.security_app import get_current_user
from database import supabase


app = APIRouter(prefix="/reports", tags=["Reports"])
 

class ReportCreateRequest(BaseModel):
    """신고 접수 요청"""

    report_type: str = Field(..., description="신고 유형: bug, content, abuse, feedback, etc.")
    content: str = Field(..., min_length=1, max_length=2000, description="신고 내용")


@app.post("/summited-report")
async def submit_report(
    data: ReportCreateRequest,
    reporter_email: str = Depends(get_current_user),
):
    """
    신고 접수.
    로그인한 사용자가 신고를 제출합니다.
    """
    try:
        row = {
            "rp_email": reporter_email,
            "report_type": data.report_type,
            "rp_content": data.content.strip(),
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
        supabase.table("reports").insert(row).execute()
        return {
            "status": "success",
            "message": "신고가 접수되었습니다.",
        }
    except Exception as e:
        print(f"❌ 신고 접수 에러: {e}")
        return {
            "status": "error",
            "message": str(e),
        }

