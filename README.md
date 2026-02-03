# 📚 AI Smart Study Assistant: Scan & Learn
> **문서 스캔부터 핵심 단어 추출, 맞춤형 퀴즈와 리워드까지 하나로 연결되는 지능형 학습 플랫폼**

본 프로젝트는 **Naver Clova OCR**과 **OpenAI GPT-4**를 결합하여 학습자의 교재를 디지털 데이터로 변환하고, 자기주도 학습을 돕는 다양한 기능을 제공하는 고성능 백엔드 시스템입니다.

---

### 🛠 기술 스택 (Technical Specifications)

| Category | Tech Stack | Details |
| :--- | :--- | :--- |
| **Language** | **Python 3.14+** | 최신 문법 및 고성능 비동기 처리 활용 |
| **Framework** | **FastAPI** | 비동기 기반의 빠르고 현대적인 API 프레임워크 |
| **AI/ML** | **Naver Clova OCR, OpenAI GPT API** | 문서 텍스트 추출 및 지능형 단어 선별/문제 생성 |
| **Database** | **PostgreSQL, SQLAlchemy** | 강력한 관계형 DB 및 효율적인 ORM 관리 |
| **Auth** | **Kakao OAuth 2.0** | 카카오 소셜 로그인을 통한 간편한 인증 체계 |
| **Testing** | **Pytest** | 견고한 로직 검증을 위한 자동화 테스트 프레임워크 |

---

## 🌟 핵심 기능 (Key Features)

### 1. 지능형 문서 분석 (AI OCR & NLP)
* **Smart Scan**: `Naver Clova OCR`을 통해 고해상도 이미지 및 PDF에서 텍스트를 정교하게 추출합니다.
* **Keyword Extraction**: GPT API를 활용해 전체 텍스트 중 학습에 필요한 **핵심 단어**만 선별적으로 추출합니다.
* **Wait Time Estimation**: 대용량 파일 분석 시, PDF 페이지 수와 이미지 개수를 계산하여 사용자에게 **실시간 예상 소요 시간**을 안내합니다.

### 2. 맞춤형 학습 도구 (Study System)
* **Blank Quiz**: 추출된 단어를 기반으로 빈칸 채우기 문제를 자동 생성합니다.
* **Multi-Level Hints**: 학습 수준에 따른 3단계 힌트 시스템을 제공합니다.
  * **초성 힌트**: 단어의 자음만 노출 (예: `ㄱㅁㄴ`)
  * **앞글자 힌트**: 단어의 앞부분 노출 (예: `제미...`)
  * **뒷글자 힌트**: 단어의 뒷부분 노출 (예: `...미니`)

### 3. 게임화 리워드 시스템 (Gamification)
* **Point Rewards**: 학습 동기 부여를 위해 다양한 활동에 리워드를 지급합니다.
  * **출석 체크**: 매일 접속 시 리워드 제공.
  * **학습 달성**: 문제 풀이 세션 완료 시 리워드 제공.
  * **복습 보너스**: 복습 시 맞춘 단어 개수에 따라 추가 리워드 제공.

### 4. 학습 통계 및 분석 (Analytics)
* **Weekly Report**: 주간 **출석률**과 **정답률**을 결합한 성취도 데이터 반환.
* **Monthly Data**: 월간 복습 횟수 및 누적 학습 데이터를 분석하여 반환.

---

## 📂 프로젝트 구조 (Project Structure)

```text
C:\bat_python
├── app/
│   ├── ocr_app.py           # Clova OCR & GPT 분석 엔드포인트
│   ├── study_app.py         # 빈칸 문제 생성 및 힌트 로직
│   ├── reward_app.py        # 출석 및 학습 리워드 관리
│   ├── weekly_app.py        # 주간/월간 통계 데이터 가공
│   └── user_app.py          # 카카오 로그인 및 사용자 관리
├── core/
│   ├── clova_ocr_service.py # OCR 엔진 통신 및 대기 시간 계산 로직
│   ├── vision_service.py    # 이미지 전처리 및 비전 서비스
│   └── notification_service.py # 알림 시스템 서비스
├── database.py              # PostgreSQL Connection 설정
└── models.py                # 유저, 리워드, 학습 데이터 DB 스키마
