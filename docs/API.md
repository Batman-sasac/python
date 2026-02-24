# API 명세 (프론트 연동용)

공통: 인증이 필요한 API는 `Authorization: Bearer <JWT>` 헤더 필요.  
Base URL 예: `http://localhost:8000` 또는 환경변수 `API_BASE_URL`.

---

## 공통·설정

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/` | 서버 상태 | - | `{ "status": "running" }` |
| GET | `/config` | OAuth/프론트 설정 | - | `{ "kakao_rest_api_key", "kakao_redirect_uri", "naver_client_id", "naver_redirect_uri" }` |

---

## Auth (prefix: `/auth`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/auth/kakao/mobile` | 카카오 콜백 (code 쿼리) | Query: `code` | HTML (앱에 code 전달) |
| POST | `/auth/kakao/mobile` | 카카오 로그인 처리 | Form: `code` | `{ "status", "token?", "email?", "nickname?", "social_id?" }` — status: `success` \| `NICKNAME_REQUIRED` |
| GET | `/auth/naver/mobile` | 네이버 콜백 | Query: `code`, `state?` | HTML |
| POST | `/auth/naver/mobile` | 네이버 로그인 처리 | Form: `code`, `state` (optional) | 동일 |
| POST | `/auth/set-nickname` | 닉네임 설정 | JSON: `{ "nickname", "email?", "social_id?" }` | `{ "status", "token", "nickname", "email", "message" }` |
| GET | `/auth/user/stats` | 사용자 학습 통계 | - | `{ "status", "data": { "total_learning_count", "consecutive_days", "monthly_goal" } }` |
| GET | `/auth/home/stats` | 홈 통계 (포인트·목표) | - | `{ "status", "data": { "points", "monthly_goal" } }` |

---

## Firebase (prefix: `/firebase`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/firebase/user/update-fcm-token` | FCM 토큰 저장 | JSON: `{ "fcm_token": string }` | `{ "status", "message" }` |

---

## 알림 (prefix 없음, notification_app)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/notification-push/update` | 복습 알림 설정 | Form: `is_notify` ("true"/"false"), `remind_time` ("HH:MM") | `{ "status", "message" }` |
| GET | `/notification-push/me` | 내 알림 설정·FCM 등록 여부 | - | `{ "status", "email", "is_notify", "remind_time", "fcm_token_registered", "message" }` |
| POST | `/notification-push/test` | 테스트 푸시 발송 | - | `{ "status", "message" }` |

---

## 리워드 (prefix 없음, reward_app)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/reward/attendance` | 출석 체크 (앱 실행 시) | - | `{ "status", "is_new_reward", "baseXP", "bonusXP", "total_points", "message" }` |
| GET | `/reward/leaderboard` | 리더보드 상위 5명 | - | `{ "status", "leaderboard": [{ "total_reward", "nickname" }] }` |

---

## 주간/목표 (prefix: `/cycle`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/cycle/set-goal` | 한달 학습 목표 설정 | Form: `cycle_count` (숫자). `token` Form은 선택( Bearer만 써도 됨) | `{ "status", "target_count", "message" }` |
| GET | `/cycle/stats/weekly-growth` | 주간 성장 그래프 | - | `{ "labels": string[], "data": number[] }` |
| GET | `/cycle/learning-stats` | 이번 달 vs 목표 | - | `{ "status", "compare": { "this_month_name", "this_month_count", "target_count", "diff" } }` |

---

## 학습/퀴즈 (prefix: `/study`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/study/grade` | 채점·리워드·저장 | JSON (GradeStudyRequest): `quiz_id`, `user_answers[]`, `correct_answers[]`, `grade_cnt`, `original_text[]?`, `keywords[]?`, `quiz_html?`, `ocr_text?`, `subject_name?`, `study_name?` | `{ "status", "score", "reward_given", "new_points" }` |
| GET | `/study/review_study/{quiz_id}` | 복습 페이지(HTML) | - | HTML |
| POST | `/study/review-study` | 복습 완료·리워드 | JSON: `{ "quiz_id", "user_answers": string[] }` | `{ "status", "new_points" }` |
| GET | `/study/hint/{quiz_id}` | 힌트 (h1/h2/h3) | - | `{ "status", "quiz_id", "data": [{ "h1","h2","h3" }] }` |

---

## OCR (prefix 없음, ocr_app)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| GET | `/ocr/usage` | OCR 사용량 | - | `{ "status", "pages_used", "pages_limit", "remaining" }` 또는 limit_reached |
| POST | `/ocr/estimate` | 예상 페이지/시간 | multipart: `file` | `{ "estimated_time": string }` |
| POST | `/ocr` | OCR 실행 | multipart: `file`, Form: `crop_x?`, `crop_y?`, `crop_width?`, `crop_height?` | `{ "status", "data": { "pages", "page_count", ... } }` |
| GET | `/ocr/quiz/{quiz_id}` | 복습용 퀴즈 데이터 | - | `{ "status", "data": { "quiz_id", "title", "extractedText", "blanks", "user_answers" } }` |
| DELETE | `/ocr/ocr-data/delete/{quiz_id}` | 학습 삭제 | - | `{ "status", "message" }` |
| GET | `/ocr/list` | 학습 목록 | - | `{ "data": [{ "id", "study_name", "subject_name", "ocr_preview", "created_at" }] }` |

---

## 신고 (prefix: `/reports`)

| Method | Path | 설명 | Request | Response |
|--------|------|------|---------|----------|
| POST | `/reports/submitted-report` | 신고 접수 (권장) | JSON: `{ "report_type": string, "content": string }` | `{ "status", "message" }` |
| POST | `/reports/summited-report` | 신고 접수 (호환용, 동일 동작) | 위와 동일 | 위와 동일 |

---

## 에러 응답 공통

- `{ "status": "error", "message": string }`
- HTTP 401: 인증 실패
- HTTP 404: 리소스 없음

프론트에서는 위 경로·메서드·Request body 키와 Response 필드를 위 명세에 맞춰 호출하면 됩니다.
