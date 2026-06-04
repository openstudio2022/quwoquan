CREATE TABLE IF NOT EXISTS otp_challenges (
  challenge_id TEXT PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE,
  phone TEXT NOT NULL,
  phone_hash TEXT NOT NULL,
  code_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ NULL,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_otp_challenges_phone_status_expires
  ON otp_challenges (phone, status, expires_at DESC);

CREATE INDEX IF NOT EXISTS idx_otp_challenges_request_id
  ON otp_challenges (request_id);
