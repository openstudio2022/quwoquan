-- GreetingRequest object packet 补齐（B3）：幂等命令回执与事务 outbox。
-- Canonical source: contracts/metadata/user/greeting_request/storage.yaml
-- receipt 修复 Send 重试语义（重试必须重放首次结果而非 duplicate_pending 409）；
-- outbox 替换 best-effort 直发，事件与状态同事务提交后由 relay 投递。

CREATE TABLE IF NOT EXISTS greeting_request_command_receipts (
    receipt_id           VARCHAR(64) PRIMARY KEY,
    actor_sub_account_id VARCHAR(64) NOT NULL,
    idempotency_key      VARCHAR(160) NOT NULL,
    operation            VARCHAR(48) NOT NULL,
    request_id           UUID NOT NULL,
    response_json        JSONB NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_gr_receipt_key UNIQUE (actor_sub_account_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS greeting_request_outbox (
    event_id     VARCHAR(96) PRIMARY KEY,
    aggregate_id UUID NOT NULL,
    event_name   VARCHAR(96) NOT NULL,
    payload_json JSONB NOT NULL,
    occurred_at  TIMESTAMPTZ NOT NULL,
    claim_owner  VARCHAR(96),
    claimed_at   TIMESTAMPTZ,
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_gr_outbox_pending
    ON greeting_request_outbox (published_at, occurred_at);
