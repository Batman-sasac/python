# python

📚 AI Smart Study Assistant: Scan & Learn
본 프로젝트는 Naver Clova OCR과 OpenAI GPT-4를 결합하여 문서 스캔부터 단어 추출, 퀴즈 생성, 그리고 학습 동기 부여를 위한 리워드 시스템까지 제공하는 지능형 자기주도 학습 플랫폼입니다.

C:\bat_python
├── app/
│   ├── ocr_app.py           # Clova OCR & GPT 단어 추출 로직
│   ├── study_app.py         # 빈칸 학습 및 힌트 시스템
│   ├── reward_app.py        # 출석/학습 리워드 포인트 로직
│   ├── weekly_app.py        # 주간/월간 통계 데이터 가공
│   └── user_app.py          # 유저 관리 및 카카오 로그인 연동
├── core/
│   ├── clova_ocr_service.py # Clova OCR API 통신 레이어
│   └── vision_service.py    # 이미지 전처리 및 비전 관련 로직
├── database.py              # DB Connection 및 Session 설정
├── models.py                # 학습 데이터, 리워드, 유저 테이블 정의
└── main.py                  # API 엔드포인트 통합 및 실행


🛠 Tech Stack
Backend: Python, FastAPI

AI Services: Naver Clova OCR, OpenAI GPT API

Database: PostgreSQL / SQLAlchemy (database.py, models.py)

Auth: Kakao OAuth (Social Login)
