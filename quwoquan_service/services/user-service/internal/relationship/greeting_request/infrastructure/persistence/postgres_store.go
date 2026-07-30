package persistence

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	generated "quwoquan_service/services/user-service/generated/relationship/greeting_request/persistence/user/persistence"
	usermodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingrepo "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
)

type PgGreetingStore struct {
	*generated.PGGreetingStoreBase
	pool *pgxpool.Pool
}

var _ greetingrepo.GreetingRequestStore = (*PgGreetingStore)(nil)

func NewPgGreetingStore(pool *pgxpool.Pool) *PgGreetingStore {
	return &PgGreetingStore{
		PGGreetingStoreBase: generated.NewPGGreetingStoreBase(pool),
		pool:                pool,
	}
}

func (s *PgGreetingStore) FindPendingBetween(ctx context.Context, requesterID, targetID string) (*usermodel.GreetingRequest, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+generated.GreetingRequestCols+`
		 FROM greeting_requests
		 WHERE requester_persona_id = $1 AND target_persona_id = $2 AND status = $3`,
		requesterID, targetID, usermodel.GreetingStatusPending)
	return generated.ScanGreetingRequest(row)
}

func (s *PgGreetingStore) FindBetween(ctx context.Context, requesterID, targetID string) (*usermodel.GreetingRequest, error) {
	row := s.pool.QueryRow(ctx,
		`SELECT `+generated.GreetingRequestCols+`
		 FROM greeting_requests
		 WHERE requester_persona_id = $1 AND target_persona_id = $2`,
		requesterID, targetID)
	return generated.ScanGreetingRequest(row)
}

func (s *PgGreetingStore) HasPendingBetween(ctx context.Context, personaA, personaB string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM greeting_requests
			WHERE status = $3
			  AND (
			    (requester_persona_id = $1 AND target_persona_id = $2)
			    OR (requester_persona_id = $2 AND target_persona_id = $1)
			  )
		)`, personaA, personaB, usermodel.GreetingStatusPending).Scan(&exists)
	return exists, err
}

func (s *PgGreetingStore) HasRepliedBetween(ctx context.Context, personaA, personaB string) (bool, error) {
	var exists bool
	err := s.pool.QueryRow(ctx, `
		SELECT EXISTS(
			SELECT 1 FROM greeting_requests
			WHERE status = $3
			  AND promoted_conversation_id IS NOT NULL
			  AND promoted_conversation_id <> ''
			  AND (
			    (requester_persona_id = $1 AND target_persona_id = $2)
			    OR (requester_persona_id = $2 AND target_persona_id = $1)
			  )
		)`, personaA, personaB, usermodel.GreetingStatusReplied).Scan(&exists)
	return exists, err
}

func (s *PgGreetingStore) ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.listByDirection(ctx, "target_persona_id", targetID, status, cursor, limit)
}

func (s *PgGreetingStore) ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]usermodel.GreetingRequest, string, error) {
	return s.listByDirection(ctx, "requester_persona_id", requesterID, status, cursor, limit)
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
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 ORDER BY created_at DESC LIMIT $2`, generated.GreetingRequestCols, column),
			subjectID, limit+1)
	} else if status != "" && cursor == "" {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3`, generated.GreetingRequestCols, column),
			subjectID, status, limit+1)
	} else if status == "" && cursor != "" {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND id < $2 ORDER BY created_at DESC LIMIT $3`, generated.GreetingRequestCols, column),
			subjectID, cursor, limit+1)
	} else {
		rows, err = s.pool.Query(ctx,
			fmt.Sprintf(`SELECT %s FROM greeting_requests WHERE %s = $1 AND status = $2 AND id < $3 ORDER BY created_at DESC LIMIT $4`, generated.GreetingRequestCols, column),
			subjectID, status, cursor, limit+1)
	}
	if err != nil {
		return nil, "", err
	}
	defer rows.Close()

	items := make([]usermodel.GreetingRequest, 0, limit+1)
	for rows.Next() {
		item, scanErr := generated.ScanGreetingRequest(rows)
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

func (s *PgGreetingStore) MarkPendingBlockedBetween(ctx context.Context, personaA, personaB string) error {
	now := time.Now().UTC()
	_, err := s.pool.Exec(ctx, `
		UPDATE greeting_requests
		SET status = $3, decision_at = $4, updated_at = $4
		WHERE status = $5
		  AND (
		    (requester_persona_id = $1 AND target_persona_id = $2)
		    OR (requester_persona_id = $2 AND target_persona_id = $1)
		  )`,
		personaA,
		personaB,
		usermodel.GreetingStatusBlocked,
		now,
		usermodel.GreetingStatusPending,
	)
	return err
}

func trimGreetingStatus(status string) string {
	if usermodel.IsGreetingRequestStatus(status) {
		return status
	}
	return ""
}
