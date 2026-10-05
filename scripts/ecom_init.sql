-- scripts/ecom_init.sql
-- 电商客服数据层（Phase 1）：客户 / 商品 / 订单 / 订单明细 / 物流轨迹 / 售后工单 / 退款审批
-- 幂等：全部 IF NOT EXISTS；由 scripts/seed_orders.py 读取执行
-- 2026-10-04

-- ── 客户 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id          UUID PRIMARY KEY,
    tenant_id   VARCHAR(64)  NOT NULL DEFAULT 'tenant_default',
    name        VARCHAR(64)  NOT NULL,
    phone       VARCHAR(20)  NOT NULL UNIQUE,
    email       VARCHAR(128),
    tier        VARCHAR(16)  NOT NULL DEFAULT 'normal',   -- normal / silver / gold
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ── 商品 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    sku               VARCHAR(32) PRIMARY KEY,             -- 如 SKU-1001
    name              VARCHAR(128) NOT NULL,
    category          VARCHAR(64)  NOT NULL,               -- 数码配件 / 智能设备 / 家用电器
    price             NUMERIC(10,2) NOT NULL,
    warranty_months   INT  NOT NULL DEFAULT 12,            -- 保修月数
    returnable        BOOLEAN NOT NULL DEFAULT TRUE,       -- 是否支持七天无理由
    unopened_required BOOLEAN NOT NULL DEFAULT FALSE,      -- 无理由是否要求未拆封（个人卫生/入耳类）
    stock             INT  NOT NULL DEFAULT 100,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 订单 ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS orders (
    id           VARCHAR(32) PRIMARY KEY,                  -- 如 A1024
    customer_id  UUID NOT NULL REFERENCES customers(id),
    status       VARCHAR(24) NOT NULL,                     -- paid / shipped / in_transit / delivered / closed / canceled
    total_amount NUMERIC(10,2) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL,
    paid_at      TIMESTAMPTZ,
    shipped_at   TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_status   ON orders(status);

-- ── 订单明细 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS order_items (
    id         BIGSERIAL PRIMARY KEY,
    order_id   VARCHAR(32) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    sku        VARCHAR(32) NOT NULL REFERENCES products(sku),
    quantity   INT NOT NULL DEFAULT 1,
    unit_price NUMERIC(10,2) NOT NULL,
    opened     BOOLEAN NOT NULL DEFAULT FALSE              -- 是否已拆封（售后规则要用）
);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);

-- ── 物流轨迹 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS logistics_tracks (
    id          BIGSERIAL PRIMARY KEY,
    order_id    VARCHAR(32) NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    track_time  TIMESTAMPTZ NOT NULL,
    location    VARCHAR(128),
    status      VARCHAR(24) NOT NULL,                      -- 已揽收 / 运输中 / 派送中 / 已签收
    description VARCHAR(256)
);
CREATE INDEX IF NOT EXISTS idx_tracks_order ON logistics_tracks(order_id);

-- ── 售后工单 ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS after_sales_tickets (
    id          VARCHAR(32) PRIMARY KEY,                   -- 如 RT-2026-1001
    order_id    VARCHAR(32) NOT NULL REFERENCES orders(id),
    customer_id UUID NOT NULL REFERENCES customers(id),
    type        VARCHAR(16) NOT NULL,                      -- refund / return / exchange
    reason      VARCHAR(256),
    status      VARCHAR(24) NOT NULL DEFAULT 'pending',    -- pending / auto_approved / pending_review / approved / rejected / closed
    auto_check  JSONB,                                     -- 规则审核结果（在保期/未拆封/金额阈值）
    amount      NUMERIC(10,2),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── 退款审批记录（HitL）────────────────────────────────
CREATE TABLE IF NOT EXISTS refund_approvals (
    id         BIGSERIAL PRIMARY KEY,
    ticket_id  VARCHAR(32) NOT NULL REFERENCES after_sales_tickets(id) ON DELETE CASCADE,
    decision   VARCHAR(16) NOT NULL,                       -- approve / modify / reject
    reviewer   VARCHAR(64),
    comment    VARCHAR(512),
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── P2 追加：审计日志 + 工单幂等键 ────────────────────────
CREATE TABLE IF NOT EXISTS audit_logs (
    id      BIGSERIAL PRIMARY KEY,
    ts      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   VARCHAR(64)  NOT NULL DEFAULT 'system',
    action  VARCHAR(64)  NOT NULL,
    target  VARCHAR(64),
    payload JSONB
);

ALTER TABLE after_sales_tickets ADD COLUMN IF NOT EXISTS idempotency_key VARCHAR(64);
CREATE UNIQUE INDEX IF NOT EXISTS uq_tickets_idempotency
    ON after_sales_tickets (idempotency_key) WHERE idempotency_key IS NOT NULL;

-- ── P4 追加：未解决问题池（转人工/低置信落库）──────────────
CREATE TABLE IF NOT EXISTS unresolved_questions (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   VARCHAR(64)  NOT NULL DEFAULT 'tenant_default',
    customer_id UUID,
    session_id  VARCHAR(128),
    question    TEXT,
    summary     TEXT,
    status      VARCHAR(24)  NOT NULL DEFAULT 'pending',   -- pending / resolved
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
