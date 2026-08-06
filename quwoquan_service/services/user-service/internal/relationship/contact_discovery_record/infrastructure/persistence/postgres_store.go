package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	generated "quwoquan_service/services/user-service/generated/relationship/contact_discovery_record/persistence/user/persistence"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/phonematch"
	"quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	repository "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/ports"
)

// PgContactDiscoveryStore extends pgContactDiscoveryStoreBase with domain-specific queries.
type PgContactDiscoveryStore struct {
	*generated.PGContactDiscoveryStoreBase
	pool *pgxpool.Pool
}

var _ repository.ContactDiscoveryStore = (*PgContactDiscoveryStore)(nil)

func NewPgContactDiscoveryStore(pool *pgxpool.Pool) *PgContactDiscoveryStore {
	return &PgContactDiscoveryStore{
		PGContactDiscoveryStoreBase: generated.NewPGContactDiscoveryStoreBase(pool),
		pool:                        pool,
	}
}

func (s *PgContactDiscoveryStore) FindLatestByOwner(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error) {
	return generated.ScanContactDiscoveryRecord(s.pool.QueryRow(ctx,
		`SELECT `+generated.ContactDiscoveryRecordCols+` FROM contact_discovery_records WHERE owner_account_id = $1 ORDER BY created_at DESC LIMIT 1`,
		ownerID))
}

func (s *PgContactDiscoveryStore) UpdateStatus(ctx context.Context, id, status string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE contact_discovery_records SET status = $2 WHERE id = $1`, id, status)
	return err
}

func (s *PgContactDiscoveryStore) CreateIdempotent(
	ctx context.Context,
	record *model.ContactDiscoveryRecord,
	dailyLimit int,
	command repository.CommandIdentity,
) (*model.ContactDiscoveryRecord, bool, error) {
	if record == nil || dailyLimit <= 0 || !validCommandIdentity(command) ||
		strings.TrimSpace(record.ID) == "" ||
		strings.TrimSpace(record.OwnerAccountID) != strings.TrimSpace(command.OwnerAccountID) ||
		record.Status != "pending" || record.ExpireAt.IsZero() {
		return nil, false, errors.New("invalid contact discovery command")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockContactCommand(ctx, tx, command); err != nil {
		return nil, false, err
	}
	if replay, found, err := replayContactCommand(ctx, tx, command); err != nil || found {
		return replay, false, err
	}
	now := time.Now().UTC()
	if record.CreatedAt.IsZero() {
		record.CreatedAt = now
	}
	if _, err := tx.Exec(
		ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		"contact-discovery-rate:"+record.OwnerAccountID+":"+record.CreatedAt.UTC().Format("2006-01-02"),
	); err != nil {
		return nil, false, err
	}
	var todayCount int
	if err := tx.QueryRow(
		ctx,
		`SELECT COUNT(*) FROM contact_discovery_records
		 WHERE owner_account_id=$1
		   AND created_at >= date_trunc('day', $2::timestamptz)
		   AND created_at < date_trunc('day', $2::timestamptz) + interval '1 day'`,
		record.OwnerAccountID,
		record.CreatedAt,
	).Scan(&todayCount); err != nil {
		return nil, false, err
	}
	if todayCount >= dailyLimit {
		return nil, false, repository.ErrRateLimited
	}
	if _, err := tx.Exec(
		ctx,
		`INSERT INTO contact_discovery_records (
		 id, owner_account_id, hashed_phones, matched_persona_ids, status,
		 match_count, expire_at, created_at, completed_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)`,
		record.ID,
		record.OwnerAccountID,
		record.HashedPhones,
		record.MatchedPersonaIds,
		record.Status,
		record.MatchCount,
		record.ExpireAt,
		record.CreatedAt,
		record.CompletedAt,
	); err != nil {
		return nil, false, err
	}
	if err := insertContactCommandReceipt(ctx, tx, command, record); err != nil {
		return nil, false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, false, err
	}
	return cloneContactRecord(record), true, nil
}

func (s *PgContactDiscoveryStore) CompleteIdempotent(
	ctx context.Context,
	recordID string,
	matchedPersonaIDs []string,
	command repository.CommandIdentity,
) (*model.ContactDiscoveryRecord, bool, error) {
	if strings.TrimSpace(recordID) == "" || !validCommandIdentity(command) {
		return nil, false, errors.New("invalid contact discovery completion")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return nil, false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockContactCommand(ctx, tx, command); err != nil {
		return nil, false, err
	}
	record, found, err := replayContactCommand(ctx, tx, command)
	if err != nil {
		return nil, false, err
	}
	if !found || record.ID != recordID {
		return nil, false, errors.New("contact discovery command receipt missing or mismatched")
	}
	if record.Status == "completed" {
		return record, false, nil
	}
	if record.Status != "pending" {
		return nil, false, fmt.Errorf("contact discovery cannot complete from %q", record.Status)
	}
	now := time.Now().UTC()
	tag, err := tx.Exec(
		ctx,
		`UPDATE contact_discovery_records
		 SET status='completed', matched_persona_ids=$2, match_count=$3, completed_at=$4
		 WHERE id=$1 AND owner_account_id=$5`,
		recordID,
		matchedPersonaIDs,
		len(matchedPersonaIDs),
		now,
		command.OwnerAccountID,
	)
	if err != nil {
		return nil, false, err
	}
	if tag.RowsAffected() != 1 {
		return nil, false, repository.ErrNotFound
	}
	record.Status = "completed"
	record.MatchedPersonaIds = append([]string(nil), matchedPersonaIDs...)
	record.MatchCount = int64(len(matchedPersonaIDs))
	record.CompletedAt = &now
	if err := updateContactCommandReceipt(ctx, tx, command, record); err != nil {
		return nil, false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, false, err
	}
	return cloneContactRecord(record), true, nil
}

func (s *PgContactDiscoveryStore) DismissIdempotent(
	ctx context.Context,
	recordID string,
	command repository.CommandIdentity,
) error {
	if strings.TrimSpace(recordID) == "" || !validCommandIdentity(command) {
		return errors.New("invalid contact discovery dismissal")
	}
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if err := lockContactCommand(ctx, tx, command); err != nil {
		return err
	}
	if replay, found, err := replayContactCommand(ctx, tx, command); err != nil || found {
		if err == nil && replay.ID != recordID {
			return repository.ErrIdempotencyConflict
		}
		return err
	}
	record, err := generated.ScanContactDiscoveryRecord(tx.QueryRow(
		ctx,
		`SELECT `+generated.ContactDiscoveryRecordCols+`
		 FROM contact_discovery_records
		 WHERE id=$1 AND owner_account_id=$2 FOR UPDATE`,
		recordID,
		command.OwnerAccountID,
	))
	if err != nil {
		return err
	}
	if record == nil {
		return repository.ErrNotFound
	}
	if record.Status != "dismissed" {
		if _, err := tx.Exec(
			ctx,
			`UPDATE contact_discovery_records SET status='dismissed' WHERE id=$1`,
			recordID,
		); err != nil {
			return err
		}
		record.Status = "dismissed"
	}
	if err := insertContactCommandReceipt(ctx, tx, command, record); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

func (s *PgContactDiscoveryStore) DeleteExpired(ctx context.Context) (int64, error) {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM contact_discovery_records WHERE expire_at < NOW()`)
	return tag.RowsAffected(), err
}

// FindPhoneMatches matches the initiator's uploaded hashes against active
// phone / carrier_phone CredentialBindings and projects matched accounts onto
// their non-strict active Personas. The stored credential_key is normalized
// plaintext; we hash it here through
// phonematch.Hash (the single client/server hashing source of truth) and
// intersect with the uploaded set, so the wire only ever carried hashes and we
// never persist or return another user's plaintext phone or ownerAccountId.
//
// Note: this scans active phone credentials per discovery. Discovery is rate
// limited (5/owner/day) so this is acceptable for launch scale; an indexed
// phone_hash column is tracked as a scale-out backlog item.
func (s *PgContactDiscoveryStore) FindPhoneMatches(ctx context.Context, hashedPhones []string) ([]model.ContactPhoneMatch, error) {
	if len(hashedPhones) == 0 {
		return []model.ContactPhoneMatch{}, nil
	}
	wanted := make(map[string]struct{}, len(hashedPhones))
	for _, h := range hashedPhones {
		if trimmed := strings.TrimSpace(h); trimmed != "" {
			wanted[trimmed] = struct{}{}
		}
	}
	if len(wanted) == 0 {
		return []model.ContactPhoneMatch{}, nil
	}

	rows, err := s.pool.Query(ctx, `
		SELECT cb.credential_key,
		       p.persona_id,
		       COALESCE(NULLIF(p.user_handle, ''), p.persona_id),
		       COALESCE(NULLIF(p.display_name, ''), NULLIF(up.owner_display_name, ''), NULLIF(up.nickname, ''), p.persona_id),
		       COALESCE(NULLIF(p.avatar_url, ''), NULLIF(up.avatar_url, ''), ''),
		       GREATEST(COALESCE(p.avatar_version, 0), COALESCE(up.avatar_version, 0)),
		       COALESCE(up.region, '')
		FROM credential_bindings cb
		INNER JOIN personas p ON p.user_id = cb.owner_id AND p.is_active = true
		INNER JOIN user_profiles up ON up.user_id = cb.owner_id
		WHERE cb.credential_type IN ('phone', 'carrier_phone')
		  AND cb.is_active = true
		  AND p.isolation_level != 'strict'
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	matches := make([]model.ContactPhoneMatch, 0)
	seen := make(map[string]struct{})
	for rows.Next() {
		var credentialKey string
		var m model.ContactPhoneMatch
		if err := rows.Scan(
			&credentialKey,
			&m.PersonaID,
			&m.UserHandle,
			&m.DisplayName,
			&m.AvatarURL,
			&m.AvatarVersion,
			&m.Region,
		); err != nil {
			return nil, err
		}
		hash := phonematch.Hash(credentialKey)
		if hash == "" {
			continue
		}
		if _, ok := wanted[hash]; !ok {
			continue
		}
		if _, dup := seen[m.PersonaID]; dup {
			continue
		}
		seen[m.PersonaID] = struct{}{}
		m.HashedPhone = hash
		matches = append(matches, m)
	}
	return matches, rows.Err()
}

func (s *PgContactDiscoveryStore) CountTodayByOwner(ctx context.Context, ownerID string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM contact_discovery_records WHERE owner_account_id = $1 AND created_at >= CURRENT_DATE`,
		ownerID).Scan(&n)
	return n, err
}

type contactCommandResult struct {
	ID                string     `json:"id"`
	OwnerAccountID    string     `json:"ownerAccountId"`
	HashedPhones      []string   `json:"hashedPhones"`
	MatchedPersonaIDs []string   `json:"matchedPersonaIds"`
	Status            string     `json:"status"`
	MatchCount        int64      `json:"matchCount"`
	ExpireAt          time.Time  `json:"expireAt"`
	CreatedAt         time.Time  `json:"createdAt"`
	CompletedAt       *time.Time `json:"completedAt"`
}

func validCommandIdentity(command repository.CommandIdentity) bool {
	if strings.TrimSpace(command.Operation) == "" ||
		strings.TrimSpace(command.OwnerAccountID) == "" ||
		strings.TrimSpace(command.IdempotencyKey) == "" ||
		len(command.IdempotencyKey) > 256 || len(command.CommandDigest) != 64 ||
		command.CommandDigest != strings.ToLower(command.CommandDigest) {
		return false
	}
	decoded, err := hex.DecodeString(command.CommandDigest)
	return err == nil && len(decoded) == sha256.Size
}

func lockContactCommand(
	ctx context.Context,
	tx pgx.Tx,
	command repository.CommandIdentity,
) error {
	_, err := tx.Exec(
		ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		strings.Join([]string{
			"contact-discovery-command", command.OwnerAccountID,
			command.Operation, command.IdempotencyKey,
		}, ":"),
	)
	return err
}

func replayContactCommand(
	ctx context.Context,
	tx pgx.Tx,
	command repository.CommandIdentity,
) (*model.ContactDiscoveryRecord, bool, error) {
	var storedDigest string
	var aggregateID string
	var resultJSON []byte
	var resultError string
	err := tx.QueryRow(
		ctx,
		`SELECT command_digest, aggregate_id, result_json, result_error
		 FROM contact_discovery_command_receipts
		 WHERE owner_account_id=$1 AND operation=$2 AND idempotency_key=$3
		 FOR UPDATE`,
		command.OwnerAccountID,
		command.Operation,
		command.IdempotencyKey,
	).Scan(&storedDigest, &aggregateID, &resultJSON, &resultError)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	if storedDigest != command.CommandDigest {
		return nil, false, repository.ErrIdempotencyConflict
	}
	if resultError != "" {
		return nil, false, fmt.Errorf("unknown contact discovery receipt result %q", resultError)
	}
	record, err := decodeContactCommandResult(resultJSON)
	if err != nil {
		return nil, false, err
	}
	if record.ID != aggregateID {
		return nil, false, errors.New("contact discovery receipt aggregate mismatch")
	}
	return record, true, nil
}

func insertContactCommandReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command repository.CommandIdentity,
	record *model.ContactDiscoveryRecord,
) error {
	resultJSON, err := encodeContactCommandResult(record)
	if err != nil {
		return err
	}
	digest := sha256.Sum256([]byte(strings.Join([]string{
		command.OwnerAccountID, command.Operation, command.IdempotencyKey,
	}, "\x00")))
	_, err = tx.Exec(
		ctx,
		`INSERT INTO contact_discovery_command_receipts (
		 receipt_id, owner_account_id, operation, idempotency_key,
		 command_digest, aggregate_id, result_status, result_json, result_error, created_at
		) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'',NOW())`,
		"cdr_"+hex.EncodeToString(digest[:]),
		command.OwnerAccountID,
		command.Operation,
		command.IdempotencyKey,
		command.CommandDigest,
		record.ID,
		record.Status,
		resultJSON,
	)
	return err
}

func updateContactCommandReceipt(
	ctx context.Context,
	tx pgx.Tx,
	command repository.CommandIdentity,
	record *model.ContactDiscoveryRecord,
) error {
	resultJSON, err := encodeContactCommandResult(record)
	if err != nil {
		return err
	}
	tag, err := tx.Exec(
		ctx,
		`UPDATE contact_discovery_command_receipts
		 SET result_status=$4, result_json=$5, result_error=''
		 WHERE owner_account_id=$1 AND operation=$2 AND idempotency_key=$3
		   AND command_digest=$6 AND aggregate_id=$7`,
		command.OwnerAccountID,
		command.Operation,
		command.IdempotencyKey,
		record.Status,
		resultJSON,
		command.CommandDigest,
		record.ID,
	)
	if err != nil {
		return err
	}
	if tag.RowsAffected() != 1 {
		return errors.New("contact discovery command receipt update lost")
	}
	return nil
}

func encodeContactCommandResult(record *model.ContactDiscoveryRecord) ([]byte, error) {
	if record == nil {
		return nil, errors.New("contact discovery command result is required")
	}
	return json.Marshal(contactCommandResult{
		ID:                record.ID,
		OwnerAccountID:    record.OwnerAccountID,
		HashedPhones:      append([]string(nil), record.HashedPhones...),
		MatchedPersonaIDs: append([]string(nil), record.MatchedPersonaIds...),
		Status:            record.Status,
		MatchCount:        record.MatchCount,
		ExpireAt:          record.ExpireAt,
		CreatedAt:         record.CreatedAt,
		CompletedAt:       record.CompletedAt,
	})
}

func decodeContactCommandResult(payload []byte) (*model.ContactDiscoveryRecord, error) {
	result := contactCommandResult{}
	if err := json.Unmarshal(payload, &result); err != nil {
		return nil, fmt.Errorf("decode contact discovery command result: %w", err)
	}
	return &model.ContactDiscoveryRecord{
		ID:                result.ID,
		OwnerAccountID:    result.OwnerAccountID,
		HashedPhones:      append([]string(nil), result.HashedPhones...),
		MatchedPersonaIds: append([]string(nil), result.MatchedPersonaIDs...),
		Status:            result.Status,
		MatchCount:        result.MatchCount,
		ExpireAt:          result.ExpireAt,
		CreatedAt:         result.CreatedAt,
		CompletedAt:       result.CompletedAt,
	}, nil
}

func cloneContactRecord(record *model.ContactDiscoveryRecord) *model.ContactDiscoveryRecord {
	if record == nil {
		return nil
	}
	copy := *record
	copy.HashedPhones = append([]string(nil), record.HashedPhones...)
	copy.MatchedPersonaIds = append([]string(nil), record.MatchedPersonaIds...)
	return &copy
}
