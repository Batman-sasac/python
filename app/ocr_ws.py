from __future__ import annotations

from typing import Any, Dict

from fastapi import WebSocket


class OcrWsManager:
    """
    OCR 진행률 WebSocket 연결 관리자.

    ## 전체 플로우(요약)
    - 프론트(클라이언트)가 `job_id`를 생성한다. (UUID 등 유니크 문자열)
    - 프론트는 OCR 요청 전에 다음 주소로 WebSocket 연결을 연다.
        - `/ws/ocr/{job_id}`
    - 프론트는 이어서 HTTP `POST /ocr` 업로드 요청을 보낼 때 FormData에 `job_id`를 함께 넣는다.
    - 서버는 OCR 처리 중 "페이지 단위 완료" 이벤트를 해당 `job_id`의 WebSocket으로 push 한다.

    ## job_id를 클라이언트가 만드는 이유
    - HTTP 업로드 요청과 WebSocket 연결을 서버에서 "같은 작업"으로 매칭하기 위해서.
    - 서버가 job_id를 발급하려면 별도 발급 API/저장소가 필요해지므로, 여기서는 클라이언트 생성 방식을 채택.
    """

    def __init__(self):
        # key: job_id, value: 해당 작업을 구독 중인 WebSocket
        self._conns: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, ws: WebSocket):
        await ws.accept()
        # 같은 job_id로 재연결하면 최신 연결로 덮어쓴다.
        self._conns[job_id] = ws

    def disconnect(self, job_id: str):
        self._conns.pop(job_id, None)

    async def send_json(self, job_id: str, payload: Dict[str, Any]):
        """
        특정 job_id 구독자에게 JSON 이벤트를 전송한다.

        payload 예시:
        {
          "type": "ocr_progress",
          "status": "page_done",
          "page": 2,
          "total_pages": 5,
          "filename": "sample.pdf"
        }
        """
        ws = self._conns.get(job_id)
        if not ws:
            return
        await ws.send_json(payload)

