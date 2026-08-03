-- OCR 페이지 쿠폰
-- DDL 단일 출처: core/entities/coupon.py (python scripts/sync_supabase_schema.py 로 적용)

create table if not exists coupons (
    id bigserial primary key,
    code text not null unique,
    benefit_type text not null default 'ocr_pages',
    benefit_value int not null check (benefit_value > 0),
    max_uses int,
    used_count int not null default 0,
    expires_at timestamptz,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists coupon_redemptions (
    id bigserial primary key,
    coupon_id bigint not null references coupons (id),
    user_email text not null,
    benefit_type text not null,
    benefit_value int not null,
    redeemed_at timestamptz not null default now(),
    unique (coupon_id, user_email)
);

create index if not exists idx_coupon_redemptions_user_email on coupon_redemptions (user_email);

-- 테스트용 (필요 시 주석 해제) — 20페이지 추가
-- insert into coupons (code, benefit_type, benefit_value, max_uses, expires_at)
-- values ('TEST20', 'ocr_pages', 20, 100, now() + interval '1 year');
