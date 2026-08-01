-- GreetingRequest typed intersection intent and server-resolved immutable snapshot.
-- Canonical source: services/user-service/contracts/relationship/greeting_request/{fields,storage}.yaml

ALTER TABLE greeting_requests
    ADD COLUMN IF NOT EXISTS intersection_ref JSONB,
    ADD COLUMN IF NOT EXISTS intersection_snapshot JSONB;
