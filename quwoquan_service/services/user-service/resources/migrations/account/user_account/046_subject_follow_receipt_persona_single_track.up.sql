-- One-time hard cutover for SubjectFollow command receipts. Earlier runtime
-- code serialized Go domain structs directly, producing PascalCase JSON keys
-- such as Follow.PersonaID. Runtime code now accepts only the canonical
-- persistence contract follow.personaId; this migration is the sole bridge.
-- Mixed, partial, unknown, or non-object shapes fail closed.

DO $do$
DECLARE
    receipt RECORD;
    follow_json JSONB;
    top_key_count INTEGER;
    follow_key_count INTEGER;
    legacy_shape BOOLEAN;
BEGIN
    FOR receipt IN
        SELECT receipt_id, response_json
        FROM subject_follow_command_receipts
    LOOP
        IF jsonb_typeof(receipt.response_json) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION
                'subject follow receipt JSON is not an object: %',
                receipt.receipt_id;
        END IF;

        SELECT COUNT(*)
        INTO top_key_count
        FROM jsonb_object_keys(receipt.response_json);

        IF top_key_count = 4
           AND receipt.response_json ?& ARRAY[
               'Follow', 'Changed', 'IdempotentReplay', 'OccurredAt'
           ] THEN
            legacy_shape := TRUE;
            follow_json := receipt.response_json -> 'Follow';
        ELSIF top_key_count = 4
              AND receipt.response_json ?& ARRAY[
                  'follow', 'changed', 'idempotentReplay', 'occurredAt'
              ] THEN
            legacy_shape := FALSE;
            follow_json := receipt.response_json -> 'follow';
        ELSE
            RAISE EXCEPTION
                'subject follow receipt JSON contains mixed, partial, or unknown top-level keys: %',
                receipt.receipt_id;
        END IF;

        IF jsonb_typeof(follow_json) IS DISTINCT FROM 'object' THEN
            RAISE EXCEPTION
                'subject follow receipt follow JSON is not an object: %',
                receipt.receipt_id;
        END IF;

        SELECT COUNT(*)
        INTO follow_key_count
        FROM jsonb_object_keys(follow_json);

        IF legacy_shape THEN
            IF follow_key_count <> 8
               OR NOT follow_json ?& ARRAY[
                   'ID', 'PersonaID', 'SubjectType', 'SubjectID',
                   'State', 'Version', 'FollowedAt', 'UpdatedAt'
               ] THEN
                RAISE EXCEPTION
                    'subject follow receipt JSON contains mixed, partial, or unknown legacy follow keys: %',
                    receipt.receipt_id;
            END IF;
        ELSIF follow_key_count <> 8
              OR NOT follow_json ?& ARRAY[
                  'id', 'personaId', 'subjectType', 'subjectId',
                  'state', 'version', 'followedAt', 'updatedAt'
              ] THEN
            RAISE EXCEPTION
                'subject follow receipt JSON contains mixed, partial, or unknown canonical follow keys: %',
                receipt.receipt_id;
        END IF;
    END LOOP;
END $do$;

UPDATE subject_follow_command_receipts
SET response_json = jsonb_build_object(
    'follow', jsonb_build_object(
        'id', response_json -> 'Follow' -> 'ID',
        'personaId', response_json -> 'Follow' -> 'PersonaID',
        'subjectType', response_json -> 'Follow' -> 'SubjectType',
        'subjectId', response_json -> 'Follow' -> 'SubjectID',
        'state', response_json -> 'Follow' -> 'State',
        'version', response_json -> 'Follow' -> 'Version',
        'followedAt', response_json -> 'Follow' -> 'FollowedAt',
        'updatedAt', response_json -> 'Follow' -> 'UpdatedAt'
    ),
    'changed', response_json -> 'Changed',
    'idempotentReplay', response_json -> 'IdempotentReplay',
    'occurredAt', response_json -> 'OccurredAt'
)
WHERE response_json ? 'Follow';
