-- Provider identifiers on federated first-login tickets move to neutral
-- slot values; brand-specific values are remapped in place. 040 stays
-- immutable because it is already applied in mutable environments.
UPDATE federated_phone_binding_tickets
SET provider = CASE provider
    WHEN 'wechat' THEN 'federated_slot_a'
    WHEN 'alipay' THEN 'federated_slot_b'
    WHEN 'qq' THEN 'federated_slot_c'
    ELSE provider
END
WHERE provider IN ('wechat', 'alipay', 'qq');

ALTER TABLE federated_phone_binding_tickets
    DROP CONSTRAINT ck_federated_phone_binding_ticket_provider;
ALTER TABLE federated_phone_binding_tickets
    ADD CONSTRAINT ck_federated_phone_binding_ticket_provider
        CHECK (provider IN ('federated_slot_a', 'federated_slot_b', 'federated_slot_c'));

ALTER TABLE federated_phone_binding_tickets
    DROP CONSTRAINT ck_federated_phone_binding_ticket_provider_identity;
ALTER TABLE federated_phone_binding_tickets
    ADD CONSTRAINT ck_federated_phone_binding_ticket_provider_identity
        CHECK (provider = credential_type);
