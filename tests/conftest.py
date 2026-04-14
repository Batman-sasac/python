"""
pytest 공통: 단위 테스트에서만 쓰는 환경 변수.

- JWT_SECRET_KEY: app 일부 모듈을 import할 때 필요할 수 있음
- Clova 관련: Clova 호출은 tests에서 mock 하므로 실제 URL은 사용하지 않음
"""
import os

os.environ.setdefault("JWT_SECRET_KEY", "unit-test-jwt-secret-do-not-use-in-prod")
os.environ.setdefault("CLOVA_OCR_URL", "https://unit-test.invalid/ocr")
os.environ.setdefault("CLOVA_OCR_SECRET", "unit-test-secret")
