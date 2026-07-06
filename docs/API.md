# API 명세 (프론트 연동용)

공통: 인증이 필요한 API는 `Authorization: Bearer <JWT>` 헤더가 필요합니다.  
Base URL 예: `http://localhost:8000` 또는 환경변수 `API_BASE_URL`.

---

## 공통·설정

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/` | 서버 상태 | - | `{ "status": "running" }` |
| GET | `/config` | OAuth/프론트 설정 | - | `{ "kakao_rest_api_key", "kakao_redirect_uri", "naver_client_id", "naver_redirect_uri" }` |

---

## Auth (`/auth`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/auth/kakao/mobile` | 카카오 콜백 (code 쿼리) | Query: `code` | HTML (앱에 code 전달) |
| POST | `/auth/kakao/mobile` | 카카오 로그인 처리 | Form: `code` | `{ "status", "token?", "email?", "nickname?", "social_id?" }` — `status`: `success` \| `NICKNAME_REQUIRED` |
| GET | `/auth/naver/mobile` | 네이버 콜백 | Query: `code`, `state?` | HTML |
| POST | `/auth/naver/mobile` | 네이버 로그인 처리 | Form: `code`, `state` (optional) | 위와 동일 |
| POST | `/auth/apple/mobile` | Apple 로그인 (iOS) | JSON: `{ "identity_token": string }` (JWT) | `{ "status", "token?", "email?", "nickname?", "social_id?" }` — `status`: `success` \| `NICKNAME_REQUIRED` |
| POST | `/auth/set-nickname` | 닉네임 설정 | JSON: `{ "nickname", "email?", "social_id?" }` | `{ "status", "token", "nickname", "email", "message" }` |
| GET | `/auth/user/stats` | 사용자 학습 통계 | - | `{ "status", "data": { "total_learning_count", "consecutive_days", "monthly_goal" } }` — `consecutive_days`는 `study_logs.completed_at` 기준(KST 날짜), `reward_service`와 동일 로직 |
| GET | `/auth/home/stats` | 홈 통계 (포인트·목표·당월 학습 횟수) | - | `{ "status", "data": { "points", "monthly_goal", "this_month_count" } }` |

---

## 푸시 토큰 (`/firebase`)

Expo 푸시 토큰 저장 (iOS, `ExponentPushToken[...]` 형식만 허용).

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/firebase/user/update-fcm-token` | Expo 푸시 토큰 저장 | JSON: `{ "fcm_token": "ExponentPushToken[...]" }` | `{ "status", "message" }` |

---

## 알림 (prefix 없음)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/notification-push/update` | 복습 알림 설정 | Form: `is_notify` (`"true"`/`"false"`, 생략 시 유지), `remind_time` (`"HH:MM"`, 생략 시 유지) | `{ "status", "message" }` |
| GET | `/notification-push/me` | 내 알림 설정·푸시 토큰 등록 여부 | - | `{ "status", "email", "is_notify", "remind_time", "fcm_token_registered", "message" }` |

---

## 리워드 (prefix 없음)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/reward/attendance` | 출석 체크 (앱 실행 시, 당일 1회) | - | `{ "status", "is_new_reward", "baseXP", "bonusXP", "total_points", "message" }` |
| GET | `/reward/leaderboard` | 리더보드 상위 5명 | - | `{ "status", "leaderboard": [{ "total_reward", "nickname" }] }` |

### 연속 학습 별도 보너스 (엔드포인트 없음)

- **학습 완료 시 자동 지급**: `POST /study/grade`, `POST /study/review-study`에서 `study_logs` 저장 후 처리 (`service/reward_service.py`).
- **조건**: 연속 학습일(KST, `study_logs` 날짜 기준) **2일 이상**이고, 당일 아직 **연속학습** 리워드가 없을 때.
- **금액**: 10P (코드 상 `STREAK_REWARD_AMOUNT`). DB `reward_history.reason` = `"연속학습"`.
- 응답 필드: 아래 학습 API의 `streak_bonus`, `consecutive_streak_days` 참고.

---

## 주간·목표 (`/cycle`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/cycle/set-goal` | 한달 학습 목표 설정 | Form: `cycle_count` (숫자, 필수). `token` Form은 선택(Bearer만 써도 됨) | `{ "status", "monthly_goal", "message" }` |
| GET | `/cycle/stats/weekly-growth` | 주간 성장 그래프 (최근 5주) | - | 성공: `{ "labels": string[], "data": number[] }` — 실패 시 `{ "error": string }` 형식일 수 있음 |
| GET | `/cycle/learning-stats` | 이번 달 vs 목표 비교 | - | `{ "status", "compare": { "this_month_name", "this_month_count", "monthly_goal", "diff" } }` |

---

## 학습·퀴즈 (`/study`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/study/grade` | 초기 채점·OCR·학습 로그·리워드 | JSON (`QuizSubmitRequest`): `quiz_id`, `user_answers[]`, `correct_answers[]`, `grade_cnt`, `page_correct_counts?`, `page_question_counts?`, `original_text[]?`, `keywords[]?`, `quiz_html?`, `ocr_text?`, `subject_name?`, `study_name?` | `{ "status", "score", "reward_given", "new_points", "streak_bonus", "consecutive_streak_days" }` — `reward_given`은 정답 리워드(정답×2). `streak_bonus`는 이번 요청에서 지급된 연속학습 보너스(0 가능). `new_points`는 모든 반영 후 총 포인트 |
| GET | `/study/review_study/{quiz_id}` | 복습 페이지(HTML) | - | HTML |
| POST | `/study/review-study` | 복습 완료·리워드 | JSON: `{ "quiz_id", "user_answers": string[] }` | `{ "status", "score", "reward_given", "new_points", "streak_bonus", "consecutive_streak_days" }` |
| GET | `/study/hint/{quiz_id}` | 힌트 (초성 등) | - | `{ "status", "quiz_id", "data": [{ "h1","h2","h3" }] }` |

---

## OCR (prefix 없음)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/ocr/usage` | OCR 사용량 | - | `{ "status", "pages_used", "pages_limit", "remaining" }` 등 |
| POST | `/ocr/estimate` | 예상 페이지/시간 | multipart: `file` | `{ "estimated_time": string }` |
| POST | `/ocr` | OCR 실행 | multipart: `file`, Form: `crop_x?`, `crop_y?`, `crop_width?`, `crop_height?`, `job_id?` | 응답 스키마·저장 흐름·2열 설정은 **[OCR.md](./OCR.md)** |
| GET | `/ocr/quiz/{quiz_id}` | 복습용 퀴즈 데이터 | - | `{ "status", "data": { "quiz_id", "title", "extractedText", "blanks", "user_answers", "pages?", "layout_meta?", "image_url?" } }` |
| DELETE | `/ocr/ocr-data/delete/{quiz_id}` | 학습 삭제 | - | `{ "status", "message" }` |
| GET | `/ocr/list` | 학습 목록 | - | `{ "data": [{ "id", "study_name", "subject_name", "ocr_preview", "created_at" }] }` |

**OCR 응답 JSON, Supabase 저장, `OCR_TWO_COLUMN_LAYOUT`, 표·레이아웃 스키마, 프론트 UI** → **[OCR.md](./OCR.md)** 에 정리해 두었습니다.

---

## 카테고리 (`/categories`)

`ocr_data.subject_name` 컬럼을 카테고리로 사용합니다. 별도 테이블 없음.

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/categories` | 학습에 카테고리 지정·변경 | JSON: `{ "quiz_id": number, "subject_name": string }` | `{ "status", "message", "data": { "quiz_id", "subject_name" } }` |
| PATCH | `/categories/rename` | 카테고리 이름 일괄 변경 | JSON: `{ "old_name": string, "new_name": string }` | `{ "status", "message", "updated_count" }` |
| GET | `/categories` | 내 카테고리 목록 (ocr_data 기준) | - | `{ "status", "data": [{ "name", "count" }] }` |

---

## 신고 (`/reports`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/reports/submitted-report` | 신고 접수 | JSON: `{ "report_type": string, "content": string }` | `{ "status", "message" }` |

---

## 에러 응답 공통

- JSON: `{ "status": "error", "message": string }` (엔드포인트에 따라 다를 수 있음)
- HTTP 401: 인증 실패
- HTTP 404: 리소스 없음

프론트에서는 위 경로·메서드·Request body 키와 Response 필드를 위 명세에 맞춰 호출하면 됩니다.
