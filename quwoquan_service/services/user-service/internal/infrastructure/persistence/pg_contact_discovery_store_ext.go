package persistence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgContactDiscoveryStore extends pgContactDiscoveryStoreBase with domain-specific queries.
type PgContactDiscoveryStore struct{ pgContactDiscoveryStoreBase }

var _ repository.ContactDiscoveryRepository = (*PgContactDiscoveryStore)(nil)

func NewPgContactDiscoveryStore(pool *pgxpool.Pool) *PgContactDiscoveryStore {
	return &PgContactDiscoveryStore{pgContactDiscoveryStoreBase{pool: pool}}
}

func (s *PgContactDiscoveryStore) FindLatestByOwner(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error) {
	return scanContactDiscoveryRecord(s.pool.QueryRow(ctx,
		`SELECT `+contactDiscoveryRecordCols+` FROM contact_discovery_records WHERE owner_account_id = $1 ORDER BY created_at DESC LIMIT 1`,
		ownerID))
}

func (s *PgContactDiscoveryStore) UpdateStatus(ctx context.Context, id, status string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE contact_discovery_records SET status = $2 WHERE id = $1`, id, status)
	return err
}

func (s *PgContactDiscoveryStore) Complete(ctx context.Context, id string, matchedSubAccountIDs []string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx,
		`UPDATE contact_discovery_records SET status = 'completed', matched_sub_account_ids = $2, match_count = $3, completed_at = $4 WHERE id = $1`,
		id, matchedSubAccountIDs, len(matchedSubAccountIDs), now)
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

// FindSubAccountIDsByPhoneHashes matches hashed phones against active credential_bindings,
// returning only subAccountId - never ownerAccountId (privacy isolation).
func (s *PgContactDiscoveryStore) FindSubAccountIDsByPhoneHashes(ctx context.Context, hashedPhones []string) ([]string, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT DISTINCT p.sub_account_id
		FROM credential_bindings cb
		INNER JOIN personas p ON p.user_id = cb.owner_id AND p.is_active = true
		WHERE cb.credential_type = 'phone'
		  AND cb.credential_key = ANY($1)
		  AND cb.is_active = true
		  AND p.isolation_level != 'strict'
	`, hashedPhones)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ids []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		ids = append(ids, id)
	}
	return ids, rows.Err()
}

func (s *PgContactDiscoveryStore) CountTodayByOwner(ctx context.Context, ownerID string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM contact_discovery_records WHERE owner_account_id = $1 AND created_at >= CURRENT_DATE`,
		ownerID).Scan(&n)
	return n, err
}
