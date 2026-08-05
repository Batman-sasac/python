-- users 테이블 OCR 한도 컬럼 (쿠폰 + ocr_usage_service 에 필요)
-- Supabase SQL Editor에서 coupons.sql 전/후 1회 실행

alter table users
    add column if not exists ocr_page_limit int;

-- 기본값은 코드에서 플랜별 월간 한도 사용. null = 보너스 0.
