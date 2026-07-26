package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
	invitationports "quwoquan_service/services/user-service/internal/account/invitation/domain/ports"
)

const invitationColumns = `id, inviter_sub_account_id, inviter_owner_account_id,
channel, link_code, COALESCE(invitee_phone_hash, ''), status, expire_at,
generated_at, delivered_at, viewed_at, accepted_at, converted_at`

type PostgresStore struct {
	pool *pgxpool.Pool
}

var _ invitationports.InvitationStore = (*PostgresStore)(nil)

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("invitation postgres pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

func (store *PostgresStore) Generate(
	ctx context.Context,
	candidate *invitationmodel.Invitation,
	dailyLimit int,
) (*invitationmodel.Invitation, bool, error) {
	if candidate == nil || dailyLimit <= 0 {
		return nil, false, invitationmodel.ErrInvalidTransition
	}
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return nil, false, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	if _, err := tx.Exec(
		ctx,
		`SELECT pg_advisory_xact_lock(hashtextextended($1, 0))`,
		"invitation:"+candidate.InviterSubAccountID,
	); err != nil {
		return nil, false, err
	}
	if candidate.InviteePhoneHash != "" {
		existing, err := scanInvitation(tx.QueryRow(
			ctx,
			`SELECT `+invitationColumns+` FROM invite_records
			 WHERE inviter_sub_account_id=$1 AND channel=$2
			   AND invitee_phone_hash=$3 AND status='generated'
			 FOR UPDATE`,
			candidate.InviterSubAccountID,
			candidate.Channel,
			candidate.InviteePhoneHash,
		))
		if err != nil {
			return nil, false, err
		}
		if existing != nil && candidate.GeneratedAt.Before(existing.ExpireAt) {
			if err := tx.Commit(ctx); err != nil {
				return nil, false, err
			}
			return existing, false, nil
		}
	}
	var todayCount int
	if err := tx.QueryRow(
		ctx,
		`SELECT COUNT(*) FROM invite_records
		 WHERE inviter_sub_account_id=$1 AND generated_at >= date_trunc('day', $2::timestamptz)`,
		candidate.InviterSubAccountID,
		candidate.GeneratedAt,
	).Scan(&todayCount); err != nil {
		return nil, false, err
	}
	if todayCount >= dailyLimit {
		return nil, false, invitationports.ErrDailyLimit
	}
	if _, err := tx.Exec(
		ctx,
		`INSERT INTO invite_records (
		 id, inviter_sub_account_id, inviter_owner_account_id, channel, link_code,
		 invitee_phone_hash, status, expire_at, generated_at, delivered_at,
		 viewed_at, accepted_at, converted_at
		) VALUES ($1,$2,$3,$4,$5,NULLIF($6,''),$7,$8,$9,$10,$11,$12,$13)`,
		candidate.ID,
		candidate.InviterSubAccountID,
		candidate.InviterOwnerAccountID,
		candidate.Channel,
		candidate.LinkCode,
		candidate.InviteePhoneHash,
		candidate.Status,
		candidate.ExpireAt,
		candidate.GeneratedAt,
		candidate.DeliveredAt,
		candidate.ViewedAt,
		candidate.AcceptedAt,
		candidate.ConvertedAt,
	); err != nil {
		return nil, false, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, false, err
	}
	copy := *candidate
	return &copy, true, nil
}

func (store *PostgresStore) FindByLinkCode(
	ctx context.Context,
	linkCode string,
) (*invitationmodel.Invitation, error) {
	record, err := scanInvitation(store.pool.QueryRow(
		ctx,
		`SELECT `+invitationColumns+` FROM invite_records WHERE link_code=$1`,
		strings.TrimSpace(linkCode),
	))
	if err != nil {
		return nil, err
	}
	if record == nil {
		return nil, invitationports.ErrNotFound
	}
	return record, nil
}

func (store *PostgresStore) ListByInviter(
	ctx context.Context,
	inviterSubAccountID string,
	status string,
	limit int,
	offset int,
) ([]invitationmodel.Invitation, error) {
	query := `SELECT ` + invitationColumns + ` FROM invite_records WHERE inviter_sub_account_id=$1`
	arguments := []any{strings.TrimSpace(inviterSubAccountID)}
	if status != "" {
		query += ` AND status=$2 ORDER BY generated_at DESC LIMIT $3 OFFSET $4`
		arguments = append(arguments, strings.TrimSpace(status), limit, offset)
	} else {
		query += ` ORDER BY generated_at DESC LIMIT $2 OFFSET $3`
		arguments = append(arguments, limit, offset)
	}
	rows, err := store.pool.Query(ctx, query, arguments...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	records := make([]invitationmodel.Invitation, 0)
	for rows.Next() {
		record, err := scanInvitation(rows)
		if err != nil {
			return nil, err
		}
		records = append(records, *record)
	}
	return records, rows.Err()
}

func (store *PostgresStore) MarkDelivered(
	ctx context.Context,
	linkCode string,
	now time.Time,
) (*invitationmodel.Invitation, error) {
	return store.transition(ctx, linkCode, now, func(record *invitationmodel.Invitation) error {
		return record.MarkDelivered(now)
	})
}

func (store *PostgresStore) Accept(
	ctx context.Context,
	linkCode string,
	now time.Time,
) (*invitationmodel.Invitation, error) {
	return store.transition(ctx, linkCode, now, func(record *invitationmodel.Invitation) error {
		return record.Accept(now)
	})
}

func (store *PostgresStore) transition(
	ctx context.Context,
	linkCode string,
	now time.Time,
	apply func(*invitationmodel.Invitation) error,
) (*invitationmodel.Invitation, error) {
	tx, err := store.pool.Begin(ctx)
	if err != nil {
		return nil, err
	}
	defer func() { _ = tx.Rollback(ctx) }()
	record, err := scanInvitation(tx.QueryRow(
		ctx,
		`SELECT `+invitationColumns+` FROM invite_records WHERE link_code=$1 FOR UPDATE`,
		strings.TrimSpace(linkCode),
	))
	if err != nil {
		return nil, err
	}
	if record == nil {
		return nil, invitationports.ErrNotFound
	}
	transitionErr := apply(record)
	if transitionErr != nil && !errors.Is(transitionErr, invitationmodel.ErrExpired) {
		return nil, transitionErr
	}
	if _, err := tx.Exec(
		ctx,
		`UPDATE invite_records
		 SET status=$2, delivered_at=$3, viewed_at=$4, accepted_at=$5,
		     converted_at=$6
		 WHERE id=$1`,
		record.ID,
		record.Status,
		record.DeliveredAt,
		record.ViewedAt,
		record.AcceptedAt,
		record.ConvertedAt,
	); err != nil {
		return nil, err
	}
	if err := tx.Commit(ctx); err != nil {
		return nil, err
	}
	if transitionErr != nil {
		return nil, transitionErr
	}
	return record, nil
}

type rowScanner interface {
	Scan(dest ...any) error
}

func scanInvitation(row rowScanner) (*invitationmodel.Invitation, error) {
	record := &invitationmodel.Invitation{}
	err := row.Scan(
		&record.ID,
		&record.InviterSubAccountID,
		&record.InviterOwnerAccountID,
		&record.Channel,
		&record.LinkCode,
		&record.InviteePhoneHash,
		&record.Status,
		&record.ExpireAt,
		&record.GeneratedAt,
		&record.DeliveredAt,
		&record.ViewedAt,
		&record.AcceptedAt,
		&record.ConvertedAt,
	)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("scan invitation: %w", err)
	}
	return record, nil
}
