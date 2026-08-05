-- OCR 월간 사용량 주기 (free=매월 20, basic/pro=구독 갱신 주기)
-- Supabase SQL Editor에서 1회 실행

alter table users
    add column if not exists ocr_page_bonus int default 0;

alter table users
    add column if not exists ocr_usage_period_end timestamptz;

alter table users
    add column if not exists ocr_usage_plan text;

comment on column users.ocr_page_bonus is '쿠폰 등으로 매월 추가되는 OCR 페이지 (플랜 한도 위)';
comment on column users.ocr_usage_period_end is '현재 OCR 사용 주기 종료 시각 (UTC). 지나면 ocrpages_used 리셋';
comment on column users.ocr_usage_plan is '마지막 리셋 시점의 플랜 (free/basic/pro)';

-- 기존 ocr_page_limit(절대값) → 보너스로 이전 (선택, 1회)
-- update users
-- set ocr_page_bonus = greatest(coalesce(ocr_page_bonus, 0), greatest(0, coalesce(ocr_page_limit, 0) - 20))
-- where ocr_page_limit is not null;
