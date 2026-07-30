package persistence

import (
	"context"
	"strings"
	"time"

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

func (s *PgContactDiscoveryStore) Complete(ctx context.Context, id string, matchedPersonaIDs []string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx,
		`UPDATE contact_discovery_records SET status = 'completed', matched_persona_ids = $2, match_count = $3, completed_at = $4 WHERE id = $1`,
		id, matchedPersonaIDs, len(matchedPersonaIDs), now)
	return err
}

func (s *PgContactDiscoveryStore) Dismiss(ctx context.Context, id string) error {
	return s.UpdateStatus(ctx, id, "dismissed")
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
