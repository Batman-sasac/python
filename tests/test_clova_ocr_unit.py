"""
Clova HTTP를 mock 하여 process_file 경로를 단위 테스트한다.

- 실제 네트워크·Gunicorn·Render 없이 OCR 후처리·키워드까지 도달하는지 확인한다.
- Gunicorn WORKER TIMEOUT 은 이 테스트로 재현하지 않는다 (통합/부하/스테이징에서 확인).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from service.clova_ocr_service import CLOVAOCRService


def _minimal_clova_json_ok() -> dict:
    """extract_text_with_clova 가 200으로 파싱하는 최소 형태 (단일 페이지, 필드 1개)."""
    return {
        "images": [
            {
                "convertedImageInfo": {"width": 400},
                "fields": [
                    {
                        "inferText": "단위테스트",
                        "boundingPoly": {
                            "vertices": [
                                {"x": 10, "y": 10},
                                {"x": 200, "y": 10},
                                {"x": 200, "y": 40},
                                {"x": 10, "y": 40},
                            ]
                        },
                    }
                ],
                "tables": None,
            }
        ]
    }


def test_process_file_success_with_mocked_clova_http():
    svc = CLOVAOCRService(api_key="sk-test-not-used")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _minimal_clova_json_ok()

    with patch("service.clova_ocr_service.requests.post", return_value=mock_resp) as post:
        out = svc.process_file(b"\xff\xd8 fake-jpeg", "test.jpg", progress_cb=None)

    post.assert_called_once()
    assert out["status"] == "success"
    assert out.get("page_count") == 1
    assert isinstance(out.get("pages"), list) and len(out["pages"]) == 1
    assert "단위테스트" in (out["pages"][0].get("original_text") or "")


def test_process_file_clova_http_error_status():
    svc = CLOVAOCRService(api_key="sk-test-not-used")
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "upstream error"

    with patch("service.clova_ocr_service.requests.post", return_value=mock_resp):
        out = svc.process_file(b"x", "a.jpg", progress_cb=None)

    assert out["status"] == "error"
    assert out.get("message")


def test_extract_text_with_clova_timeout_returns_none():
    svc = CLOVAOCRService(api_key="sk-test-not-used")

    with patch("service.clova_ocr_service.requests.post", side_effect=requests.Timeout):
        raw = svc.extract_text_with_clova(b"x", "t.jpg", progress_cb=None)

    assert raw is None
