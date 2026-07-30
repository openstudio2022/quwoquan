-- One-time, data-preserving hard cutover from the retired split-actor
-- vocabulary to the canonical Persona vocabulary. Historical migrations stay
-- byte-stable because their checksums may already exist in production ledgers;
-- fresh databases apply those immutable files and then converge here.
--
-- This is a migration only. Runtime code must never dual-read or dual-write the
-- retired columns. A partially migrated table fails closed instead of choosing
-- one of two identities.

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'user_profiles'
          AND column_name = 'sub_account_count'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'user_profiles'
          AND column_name = 'persona_count'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'user_profiles contains both retired and canonical actor columns';
    ELSIF old_exists THEN
        ALTER TABLE user_profiles RENAME COLUMN sub_account_count TO persona_count;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'user_profiles has no actor count column to migrate';
    END IF;
END $do$;

-- Greeting command receipts remain replayable after the hard cutover.  The
-- stored result is the full GreetingRequest JSON, so renaming only the SQL
-- columns would make an old receipt decode with empty requester/target IDs.
-- Accept exactly one complete vocabulary, reject mixed/partial objects, then
-- rewrite the two top-level keys without changing any other JSON value.
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM greeting_request_command_receipts
        WHERE jsonb_typeof(response_json) IS DISTINCT FROM 'object'
           OR NOT (
                (
                    response_json ? 'requesterSubAccountId'
                    AND response_json ? 'targetSubAccountId'
                    AND NOT (response_json ? 'requesterPersonaId')
                    AND NOT (response_json ? 'targetPersonaId')
                )
                OR
                (
                    response_json ? 'requesterPersonaId'
                    AND response_json ? 'targetPersonaId'
                    AND NOT (response_json ? 'requesterSubAccountId')
                    AND NOT (response_json ? 'targetSubAccountId')
                )
           )
    ) THEN
        RAISE EXCEPTION
            'greeting receipt JSON contains mixed, partial, or non-object actor identity keys';
    END IF;

    UPDATE greeting_request_command_receipts
    SET response_json =
        (response_json - 'requesterSubAccountId' - 'targetSubAccountId')
        || jsonb_build_object(
            'requesterPersonaId', response_json -> 'requesterSubAccountId',
            'targetPersonaId', response_json -> 'targetSubAccountId'
        )
    WHERE response_json ? 'requesterSubAccountId'
      AND response_json ? 'targetSubAccountId';
END $do$;

-- Only unpublished outbox rows can still be delivered by the current relay.
-- Published rows are immutable event history; pending rows must be canonical
-- before startup continues, otherwise the relay would route to empty actors.
DO $do$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM greeting_request_outbox
        WHERE published_at IS NULL
          AND (
              jsonb_typeof(payload_json) IS DISTINCT FROM 'object'
              OR NOT (
                    (
                        payload_json ? 'requesterSubAccountId'
                        AND payload_json ? 'targetSubAccountId'
                        AND NOT (payload_json ? 'requesterPersonaId')
                        AND NOT (payload_json ? 'targetPersonaId')
                    )
                    OR
                    (
                        payload_json ? 'requesterPersonaId'
                        AND payload_json ? 'targetPersonaId'
                        AND NOT (payload_json ? 'requesterSubAccountId')
                        AND NOT (payload_json ? 'targetSubAccountId')
                    )
              )
          )
    ) THEN
        RAISE EXCEPTION
            'pending greeting outbox JSON contains mixed, partial, or non-object actor identity keys';
    END IF;

    UPDATE greeting_request_outbox
    SET payload_json =
        (payload_json - 'requesterSubAccountId' - 'targetSubAccountId')
        || jsonb_build_object(
            'requesterPersonaId', payload_json -> 'requesterSubAccountId',
            'targetPersonaId', payload_json -> 'targetSubAccountId'
        )
    WHERE published_at IS NULL
      AND payload_json ? 'requesterSubAccountId'
      AND payload_json ? 'targetSubAccountId';
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'personas'
          AND column_name = 'sub_account_id'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'personas'
          AND column_name = 'persona_id'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'personas contains both retired and canonical identity columns';
    ELSIF old_exists THEN
        ALTER TABLE personas RENAME COLUMN sub_account_id TO persona_id;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'personas has no identity column to migrate';
    END IF;
END $do$;

DO $do$
BEGIN
    IF to_regclass('idx_personas_sub_account_id') IS NOT NULL
       AND to_regclass('idx_personas_persona_id') IS NOT NULL THEN
        RAISE EXCEPTION 'personas contains both retired and canonical identity indexes';
    ELSIF to_regclass('idx_personas_sub_account_id') IS NOT NULL THEN
        ALTER INDEX idx_personas_sub_account_id RENAME TO idx_personas_persona_id;
    END IF;
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'personas'::regclass
          AND conname = 'uq_personas_sub_account_id'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'personas'::regclass
          AND conname = 'uq_personas_persona_id'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'personas contains both retired and canonical identity constraints';
    ELSIF old_exists THEN
        ALTER TABLE personas
            RENAME CONSTRAINT uq_personas_sub_account_id TO uq_personas_persona_id;
    END IF;
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'contact_discovery_records'
          AND column_name = 'matched_sub_account_ids'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'contact_discovery_records'
          AND column_name = 'matched_persona_ids'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'contact_discovery_records contains both retired and canonical match columns';
    ELSIF old_exists THEN
        ALTER TABLE contact_discovery_records
            RENAME COLUMN matched_sub_account_ids TO matched_persona_ids;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'contact_discovery_records has no matched actor column to migrate';
    END IF;
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_request_command_receipts'
          AND column_name = 'actor_sub_account_id'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_request_command_receipts'
          AND column_name = 'actor_persona_id'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'greeting receipts contain both retired and canonical actor columns';
    ELSIF old_exists THEN
        ALTER TABLE greeting_request_command_receipts
            RENAME COLUMN actor_sub_account_id TO actor_persona_id;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'greeting receipts have no actor column to migrate';
    END IF;
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'invite_records'
          AND column_name = 'inviter_sub_account_id'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'invite_records'
          AND column_name = 'inviter_persona_id'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'invite_records contains both retired and canonical inviter columns';
    ELSIF old_exists THEN
        ALTER TABLE invite_records
            RENAME COLUMN inviter_sub_account_id TO inviter_persona_id;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'invite_records has no inviter column to migrate';
    END IF;
END $do$;

DO $do$
BEGIN
    IF to_regclass('idx_invite_records_inviter_sub') IS NOT NULL
       AND to_regclass('idx_invite_records_inviter_persona') IS NOT NULL THEN
        RAISE EXCEPTION 'invite_records contains both retired and canonical inviter indexes';
    ELSIF to_regclass('idx_invite_records_inviter_sub') IS NOT NULL THEN
        ALTER INDEX idx_invite_records_inviter_sub
            RENAME TO idx_invite_records_inviter_persona;
    END IF;
END $do$;

DO $do$
DECLARE
    requester_old BOOLEAN;
    requester_canonical BOOLEAN;
    target_old BOOLEAN;
    target_canonical BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_requests'
          AND column_name = 'requester_sub_account_id'
    ) INTO requester_old;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_requests'
          AND column_name = 'requester_persona_id'
    ) INTO requester_canonical;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_requests'
          AND column_name = 'target_sub_account_id'
    ) INTO target_old;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'greeting_requests'
          AND column_name = 'target_persona_id'
    ) INTO target_canonical;

    IF requester_old AND requester_canonical THEN
        RAISE EXCEPTION 'greeting_requests contains both requester actor columns';
    ELSIF requester_old THEN
        ALTER TABLE greeting_requests
            RENAME COLUMN requester_sub_account_id TO requester_persona_id;
    ELSIF NOT requester_canonical THEN
        RAISE EXCEPTION 'greeting_requests has no requester actor column to migrate';
    END IF;

    IF target_old AND target_canonical THEN
        RAISE EXCEPTION 'greeting_requests contains both target actor columns';
    ELSIF target_old THEN
        ALTER TABLE greeting_requests
            RENAME COLUMN target_sub_account_id TO target_persona_id;
    ELSIF NOT target_canonical THEN
        RAISE EXCEPTION 'greeting_requests has no target actor column to migrate';
    END IF;
END $do$;

DO $do$
DECLARE
    old_exists BOOLEAN;
    canonical_exists BOOLEAN;
    invalid_style_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'profile_qr_tokens'
          AND column_name = 'sub_account_id'
    ) INTO old_exists;
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'profile_qr_tokens'
          AND column_name = 'persona_id'
    ) INTO canonical_exists;
    IF old_exists AND canonical_exists THEN
        RAISE EXCEPTION 'profile_qr_tokens contains both retired and canonical identity columns';
    ELSIF old_exists THEN
        ALTER TABLE profile_qr_tokens
            RENAME COLUMN sub_account_id TO persona_id;
    ELSIF NOT canonical_exists THEN
        RAISE EXCEPTION 'profile_qr_tokens has no identity column to migrate';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'profile_qr_tokens'
          AND column_name = 'style_version'
    ) THEN
        EXECUTE $sql$
            SELECT EXISTS (
                SELECT 1 FROM profile_qr_tokens
                WHERE style_version IS DISTINCT FROM 'v1'
            )
        $sql$ INTO invalid_style_exists;
        IF invalid_style_exists THEN
            RAISE EXCEPTION 'profile_qr_tokens contains unsupported style variants';
        END IF;
        ALTER TABLE profile_qr_tokens DROP COLUMN style_version;
    END IF;
END $do$;
