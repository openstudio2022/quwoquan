package persistence

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	"quwoquan_service/services/user-service/internal/domain/user/repository"
)

// PgInviteStore extends pgInviteStoreBase with domain-specific queries.
type PgInviteStore struct{ pgInviteStoreBase }

var _ repository.InviteRepository = (*PgInviteStore)(nil)

func NewPgInviteStore(pool *pgxpool.Pool) *PgInviteStore {
	return &PgInviteStore{pgInviteStoreBase{pool: pool}}
}

func (s *PgInviteStore) FindByLinkCode(ctx context.Context, linkCode string) (*model.InviteRecord, error) {
	return scanInviteRecord(s.pool.QueryRow(ctx,
		`SELECT `+inviteRecordCols+` FROM invite_records WHERE link_code = $1`, linkCode))
}

// FindIdempotent finds a 'generated' invite for the same (inviter, channel, inviteePhone) triple.
func (s *PgInviteStore) FindIdempotent(ctx context.Context, inviterSubAccountID, channel, inviteePhoneHash string) (*model.InviteRecord, error) {
	return scanInviteRecord(s.pool.QueryRow(ctx,
		`SELECT `+inviteRecordCols+` FROM invite_records
		 WHERE inviter_sub_account_id = $1 AND channel = $2 AND invitee_phone_hash = $3 AND status = 'generated'`,
		inviterSubAccountID, channel, inviteePhoneHash))
}

func (s *PgInviteStore) UpdateStatus(ctx context.Context, id, status string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE invite_records SET status = $2 WHERE id = $1`, id, status)
	return err
}

func (s *PgInviteStore) MarkDelivered(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE invite_records SET delivered_at = $2, status = 'delivered' WHERE id = $1 AND delivered_at IS NULL`,
		id, time.Now().UTC())
	return err
}

func (s *PgInviteStore) MarkViewed(ctx context.Context, id string) error {
	_, err := s.pool.Exec(ctx,
		`UPDATE invite_records SET viewed_at = $2, status = 'viewed' WHERE id = $1 AND viewed_at IS NULL`,
		id, time.Now().UTC())
	return err
}

func (s *PgInviteStore) Accept(ctx context.Context, id string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx,
		`UPDATE invite_records SET accepted_at = $2, status = 'accepted' WHERE id = $1 AND status NOT IN ('accepted','expired')`,
		id, now)
	return err
}

func (s *PgInviteStore) Convert(ctx context.Context, id string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx,
		`UPDATE invite_records SET converted_at = $2, status = 'converted' WHERE id = $1 AND status = 'accepted'`,
		id, now)
	return err
}

func (s *PgInviteStore) ListByInviter(ctx context.Context, inviterSubAccountID, statusFilter string, limit, offset int) ([]model.InviteRecord, error) {
	query := `SELECT ` + inviteRecordCols + ` FROM invite_records WHERE inviter_sub_account_id = $1`
	args := []any{inviterSubAccountID}
	if statusFilter != "" {
		query += ` AND status = $2 ORDER BY generated_at DESC LIMIT $3 OFFSET $4`
		args = append(args, statusFilter, limit, offset)
	} else {
		query += ` ORDER BY generated_at DESC LIMIT $2 OFFSET $3`
		args = append(args, limit, offset)
	}

	rows, err := s.pool.Query(ctx, query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var result []model.InviteRecord
	for rows.Next() {
		var e model.InviteRecord
		if err := rows.Scan(&e.ID, &e.InviterSubAccountID, &e.InviterOwnerAccountID, &e.Channel, &e.LinkCode,
			&e.InviteePhoneHash, &e.Status, &e.ExpireAt, &e.GeneratedAt,
			&e.DeliveredAt, &e.ViewedAt, &e.AcceptedAt, &e.ConvertedAt); err != nil {
			return nil, err
		}
		result = append(result, e)
	}
	return result, rows.Err()
}

func (s *PgInviteStore) CountTodayByInviter(ctx context.Context, inviterSubAccountID string) (int, error) {
	var n int
	err := s.pool.QueryRow(ctx,
		`SELECT COUNT(*) FROM invite_records WHERE inviter_sub_account_id = $1 AND generated_at >= CURRENT_DATE`,
		inviterSubAccountID).Scan(&n)
	return n, err
}
