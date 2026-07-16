package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	usermodel "quwoquan_service/services/user-service/internal/domain/user/model"
	greetingrepo "quwoquan_service/services/user-service/internal/domain/user/ports"
)

type PgGreetingStore struct{ pgGreetingStoreBase }

var _ greetingrepo.GreetingRequestStore = (*PgGreetingStore)(nil)

func NewPgGreetingStore(pool *pgxpool.Pool) *PgGreetingStore {
	return &PgGreetingStore{pgGreetingStoreBase{pool: pool}}
}

func (s *PgGreetingStore) FindPendingBetween(ctx context.Context, requesterID, targetID string) (*usermodel.GreetingRequest, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+greetingRequestCols+`
		 FROM greeting_requests
		 WHERE requester_sub_account_id = $1 AND target_sub_account_id = $2 AND status = 'pending'`,
		requesterID, targetID)
	return scanGreetingRequest(row)
}

func (s *PgGreetingStore) FindBetween(ctx context.Context, requesterID, targetID string) (*usermodel.GreetingRequest, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+greetingRequestCols+`
		 FROM greeting_requests
		 WHERE requester_sub_account_id = $1 AND target_sub_account_id = $2`,
		requesterID, targetID)
	return scanGreetingRequest(row)
}

func (s *PgGreetingStore) HasPendingBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM greeting_requests
			WHERE status = 'pending'
			  AND (
			    (requester_sub_account_id = $1 AND target_sub_account_id = $2)
			    OR (requester_sub_account_id = $2 AND target_sub_account_id = $1)
			  )
		)`, subAccountA, subAccountB).Scan(&exists)
	return exists, err
}

func (s *PgGreetingStore) HasRepliedBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM greeting_requests
			WHERE status = 'replied'
			  AND promoted_conversation_id IS NOT NULL
			  AND promoted_conversation_id <> ''
			  AND (
			    (requester_sub_account_id = $1 AND target_sub_account_id = $2)
			    OR (requester_sub_account_id = $2 AND target_sub_account_id = $1)
			  )
		)`, subAccountA, subAccountB).Scan(&exists)
	return exists, err
}

func (s *PgGreetingStore) ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.listByDirection(ctx, "target_sub_account_id", targetID, status, cursor, limit)
}

func (s *PgGreetingStore) ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.listByDirection(ctx, "requester_sub_account_id", requesterID, status, cursor, limit)
}

func (s *PgGreetingStore) listByDirection(
	ctx context.Context,
	column, subjectID, status, cursor string,
	limit int,
) ([]usermodel.GreetingRequest, string, error) {
	if limit <= 0 {
		limit = 20
	}
	status = trimGreetingStatus(status)
	var rows pgx.Rows
	var err error
	if status == "" && cursor == "" {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 ORDER BY created_at DESC LIMIT $2`, greetingRequestCols, column),
			subjectID, limit+1)
	} else if status != "" && cursor == "" {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3`, greetingRequestCols, column),
			subjectID, status, limit+1)
	} else if status == "" && cursor != "" {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND id < $2 ORDER BY created_at DESC LIMIT $3`, greetingRequestCols, column),
			subjectID, cursor, limit+1)
	} else {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND status = $2 AND id < $3 ORDER BY created_at DESC LIMIT $4`, greetingRequestCols, column),
			subjectID, status, cursor, limit+1)
	}
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()

	items := make([]usermodel.GreetingRequest, 0, limit+1)
	for rows.Next() {
		item, scanErr := scanGreetingRequest(rows)
		if scanErr != nil {
			return nil, "", scanErr
		}
		if item != nil {
			items = append(items, *item)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, "", err
	}
	nextCursor := ""
	if len(items) > limit {
		nextCursor = items[limit].ID
		items = items[:limit]
	}
	return items, nextCursor, nil
}

func (s *PgGreetingStore) MarkPendingBlockedBetween(ctx context.Context, subAccountA, subAccountB string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx, `
		UPDATE greeting_requests
		SET status = 'blocked', decision_at = $3, updated_at = $3
		WHERE status = 'pending'
		  AND (
		    (requester_sub_account_id = $1 AND target_sub_account_id = $2)
		    OR (requester_sub_account_id = $2 AND target_sub_account_id = $1)
		  )`, subAccountA, subAccountB, now)
	return err
}

func trimGreetingStatus(status string) string {
	switch status {
	case "pending", "replied", "ignored", "blocked", "cancelled", "expired":
		return status
	default:
		return ""
	}
}
