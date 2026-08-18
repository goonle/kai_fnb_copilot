-- ============================================================
-- Harbour Street Cafe / Nonna's Trattoria - 멀티테넌트 스키마
-- Snowflake DDL
-- 금액 컬럼은 전부 "숫자(_NUMBER)" + "통화단위(_UNIT)" 두 컬럼으로 분리
-- (향후 다른 국가/통화로 확장 시 대비)
-- ============================================================

CREATE DATABASE IF NOT EXISTS HARBOUR_CAFE;
USE DATABASE HARBOUR_CAFE;

CREATE SCHEMA IF NOT EXISTS RAW;
USE SCHEMA RAW;

-- ------------------------------------------------------------
-- 1. businesses : 비즈니스(매장) 마스터
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.BUSINESSES (
    BUSINESS_ID     VARCHAR(20)     NOT NULL PRIMARY KEY,
    BUSINESS_NAME   VARCHAR(200)    NOT NULL,
    BUSINESS_TYPE   VARCHAR(200),
    CITY            VARCHAR(100),
    COUNTRY         VARCHAR(100),
    CREATED_AT      DATE
);

-- ------------------------------------------------------------
-- 2. ingredients : 재료 카탈로그 (재료당 1행, 공유 참조 테이블)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.INGREDIENTS (
    INGREDIENT_ID   VARCHAR(10)     NOT NULL PRIMARY KEY,
    INGREDIENT_NAME VARCHAR(200)    NOT NULL,
    CATEGORY        VARCHAR(100),      -- 예: Fresh Seafood, Fresh Meat, Asian Specialty Imports
    STANDARD_UNIT   VARCHAR(20),       -- kg, L, ea 등 (수량 단위, 통화 아님)
    WASTE_PCT       NUMBER(5,2)     DEFAULT 5.00   -- spoilage/waste %, accounts for human error in kitchen
);

-- ------------------------------------------------------------
-- 3. vendor_offerings : 벤더 x 재료 조합 (같은 재료를 여러 벤더가 판매)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.VENDOR_OFFERINGS (
    VENDOR_NAME          VARCHAR(200)    NOT NULL,
    INGREDIENT_ID        VARCHAR(10)     NOT NULL REFERENCES RAW.INGREDIENTS(INGREDIENT_ID),
    PURCHASE_UNIT        VARCHAR(20),      -- kg, L, ea, pkt(...)
    PACK_SIZE            NUMBER(10,2),     -- 1 pack = 이 만큼의 purchase_unit
    UNIT_PRICE_NUMBER    NUMBER(10,2),     -- 단가 숫자
    UNIT_PRICE_UNIT      VARCHAR(3)      DEFAULT 'NZD',   -- 통화 단위
    PRIMARY KEY (VENDOR_NAME, INGREDIENT_ID)
);

-- ------------------------------------------------------------
-- 4. items : 비즈니스별 판매 품목 (메뉴+음료 통합, item_type으로 구분)
--    item_id를 서로게이트 키로 부여 (예: HSC001-I001)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.ITEMS (
    BUSINESS_ID       VARCHAR(20)     NOT NULL REFERENCES RAW.BUSINESSES(BUSINESS_ID),
    ITEM_ID           VARCHAR(20)     NOT NULL PRIMARY KEY,
    ITEM_NAME         VARCHAR(200)    NOT NULL,
    ITEM_TYPE         VARCHAR(10)     NOT NULL,   -- 'food' 또는 'drink'
    CATEGORY          VARCHAR(100),      -- 예: Sushi, Don, Pizza, Drink
    PRICE_NUMBER      NUMBER(10,2)    NOT NULL,   -- 가격 숫자
    PRICE_UNIT        VARCHAR(3)      DEFAULT 'NZD',   -- 통화 단위
    AVG_DAILY_QTY     NUMBER(10,2)       -- 기준 일 평균 판매량 (시뮬레이션 파라미터)
);

-- ------------------------------------------------------------
-- 5. menu_ingredient_tags : 메뉴-재료 태깅 (정밀 그램 수 없음, 단순 연관관계)
--    실제 조리 현장에서 정밀 계량이 어려운 점을 반영해
--    "이 메뉴는 이 재료가 들어간다"는 사실만 기록.
--    구매↔판매 상관관계는 그램 단위 소비량 역산이 아니라
--    "같은 재료가 태깅된 메뉴들의 판매량 합계" vs "그 재료의 구매량 추이"를
--    같은 기간에 나란히 비교하는 방식으로 분석.
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.MENU_INGREDIENT_TAGS (
    BUSINESS_ID     VARCHAR(20)   NOT NULL,
    ITEM_ID         VARCHAR(20)   NOT NULL REFERENCES RAW.ITEMS(ITEM_ID),
    INGREDIENT      VARCHAR(200)  NOT NULL,   -- ingredients.ingredient_name 과 텍스트 매칭
    INGREDIENT_ID   VARCHAR(10)   REFERENCES RAW.INGREDIENTS(INGREDIENT_ID)
);

-- ------------------------------------------------------------
-- 6. purchase_ledger : 구매 원장 (실제 벤더로부터 산 기록)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.PURCHASE_LEDGER (
    BUSINESS_ID          VARCHAR(20)    NOT NULL REFERENCES RAW.BUSINESSES(BUSINESS_ID),
    WEEK_START           DATE           NOT NULL,
    VENDOR               VARCHAR(200)   NOT NULL,
    INGREDIENT           VARCHAR(200)   NOT NULL,
    INGREDIENT_ID        VARCHAR(10)    REFERENCES RAW.INGREDIENTS(INGREDIENT_ID),
    QTY_PACKS            NUMBER(10,2)   NOT NULL,
    PACK_SIZE            NUMBER(10,2),
    UNIT                 VARCHAR(20),
    UNIT_PRICE_NUMBER    NUMBER(10,2),                    -- 단가 숫자
    UNIT_PRICE_UNIT      VARCHAR(3)     DEFAULT 'NZD',    -- 통화 단위
    LINE_TOTAL_NUMBER    NUMBER(12,2)   NOT NULL,          -- 라인 합계 숫자
    LINE_TOTAL_UNIT       VARCHAR(3)     DEFAULT 'NZD'     -- 통화 단위
);

-- ------------------------------------------------------------
-- 7. daily_sales : 일별 판매(cash-up) 상세
--    category는 items 테이블에서 join으로 조회 (중복 제거)
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.DAILY_SALES (
    BUSINESS_ID              VARCHAR(20)   NOT NULL REFERENCES RAW.BUSINESSES(BUSINESS_ID),
    SALE_DATE                DATE          NOT NULL,   -- CSV의 'date' -> 예약어 회피 위해 SALE_DATE로
    ITEM_ID                  VARCHAR(20)   NOT NULL REFERENCES RAW.ITEMS(ITEM_ID),
    QTY_SOLD_FULL_PRICE      NUMBER(10,2),
    QTY_SOLD_DISCOUNTED      NUMBER(10,2),
    DISCOUNT_RATE            NUMBER(5,2),                 -- 0.00 ~ 0.30 (비율, 통화 아님)
    UNIT_PRICE_NUMBER        NUMBER(10,2),                -- 단가 숫자
    UNIT_PRICE_UNIT          VARCHAR(3)    DEFAULT 'NZD', -- 통화 단위
    REVENUE_NUMBER           NUMBER(12,2)  NOT NULL,       -- 매출 숫자
    REVENUE_UNIT             VARCHAR(3)    DEFAULT 'NZD'   -- 통화 단위
);

-- ------------------------------------------------------------
-- 8. price_alerts : 가격 변동 알림 기록
-- ------------------------------------------------------------
CREATE OR REPLACE TABLE RAW.PRICE_ALERTS (
    ALERT_ID            VARCHAR(20)     NOT NULL PRIMARY KEY,
    BUSINESS_ID         VARCHAR(20)     NOT NULL REFERENCES RAW.BUSINESSES(BUSINESS_ID),
    INGREDIENT_ID       VARCHAR(10)     REFERENCES RAW.INGREDIENTS(INGREDIENT_ID),
    INGREDIENT_NAME     VARCHAR(200)    NOT NULL,
    VENDOR_NAME         VARCHAR(200)    NOT NULL,
    OLD_PRICE_NUMBER    NUMBER(10,2),
    NEW_PRICE_NUMBER    NUMBER(10,2)    NOT NULL,
    PRICE_UNIT          VARCHAR(3)      DEFAULT 'NZD',
    CHANGE_PCT          NUMBER(5,2),
    ALTERNATIVE_VENDOR  VARCHAR(200),
    ALTERNATIVE_PRICE   NUMBER(10,2),
    EST_MONTHLY_IMPACT  NUMBER(12,2),
    STATUS              VARCHAR(20)     DEFAULT 'pending',
    CREATED_AT          TIMESTAMP_NTZ   DEFAULT CURRENT_TIMESTAMP()
);
