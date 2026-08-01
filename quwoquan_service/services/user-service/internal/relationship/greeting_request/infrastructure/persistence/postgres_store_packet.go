package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	usermodel "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/model"
	greetingrepo "quwoquan_service/services/user-service/internal/relationship/greeting_request/domain/ports"
)

// GreetingRequest 对象 packet 扩展：state、幂等 receipt 与事务 outbox 在
// 同一 PostgreSQL 事务提交；事件由 relay 消费 outbox 后投递，命令路径不再
// best-effort 直发。

var _ greetingrepo.GreetingCommandStore = (*PgGreetingStore)(nil)
var _ greetingrepo.GreetingOutbox = (*PgGreetingStore)(nil)

func (s *PgGreetingStore) LoadCommandReceipt(
	ctx context.Context,
	actorPersonaID, idempotencyKey, operation string,
) (*usermodel.GreetingRequest, bool, error) {
	var (
		storedOperation string
		payload         []byte
	)
	err := s.pool.QueryRow(ctx, `
		SELECT operation, response_json
		FROM greeting_request_command_receipts
		WHERE actor_persona_id = $1 AND idempotency_key = $2`,
		actorPersonaID, idempotencyKey,
	).Scan(&storedOperation, &payload)
	if errors.Is(err, pgx.ErrNoRows) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, fmt.Errorf("load greeting receipt: %w", err)
	}
	if storedOperation != operation {
		return nil, false, errors.New("greeting idempotency key was reused with a different command")
	}
	var greeting usermodel.GreetingRequest
	if err := json.Unmarshal(payload, &greeting); err != nil {
		return nil, false, fmt.Errorf("decode greeting receipt: %w", err)
	}
	return &greeting, true, nil
}

// CommitCommand 在单事务内提交 greeting state（insert 或 update）、幂等
// receipt 与 outbox 事件。
func (s *PgGreetingStore) CommitCommand(
	ctx context.Context,
	commit greetingrepo.GreetingCommit,
) error {
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("begin greeting command transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback(ctx)
		}
	}()

	greeting := commit.Greeting
	if commit.Insert {
		if _, err := tx.Exec(ctx, `
			INSERT INTO greeting_requests (
				id, requester_persona_id, target_persona_id, request_message,
				intersection_ref, intersection_snapshot,
				status, source, promoted_conversation_id, expire_at, decision_at,
				created_at, updated_at
			) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())`,
			greeting.ID, greeting.RequesterPersonaID, greeting.TargetPersonaID,
			greeting.RequestMessage, nullableJSON(greeting.IntersectionRef),
			nullableJSON(greeting.IntersectionSnapshot), greeting.Status, greeting.Source,
			greeting.PromotedConversationID, greeting.ExpireAt, greeting.DecisionAt,
		); err != nil {
			return fmt.Errorf("insert greeting request: %w", err)
		}
	} else {
		tag, err := tx.Exec(ctx, `
			UPDATE greeting_requests
			SET status = $2, promoted_conversation_id = $3, decision_at = $4, updated_at = NOW()
			WHERE id = $1`,
			greeting.ID, greeting.Status,
			greeting.PromotedConversationID, greeting.DecisionAt,
		)
		if err != nil {
			return fmt.Errorf("update greeting request: %w", err)
		}
		if tag.RowsAffected() != 1 {
			return errors.New("greeting request changed before commit")
		}
	}

	if commit.IdempotencyKey != "" {
		payload, err := json.Marshal(greeting)
		if err != nil {
			return fmt.Errorf("encode greeting receipt: %w", err)
		}
		if _, err := tx.Exec(ctx, `
			INSERT INTO greeting_request_command_receipts (
				receipt_id, actor_persona_id, idempotency_key, operation, request_id, response_json, created_at
			) VALUES ($1, $2, $3, $4, $5, $6, NOW())`,
			"grr_"+uuid.NewString(), commit.ActorPersonaID, commit.IdempotencyKey,
			commit.Operation, greeting.ID, payload,
		); err != nil {
			return fmt.Errorf("save greeting receipt: %w", err)
		}
	}

	eventPayload, err := json.Marshal(commit.EventPayload)
	if err != nil {
		return fmt.Errorf("encode greeting outbox payload: %w", err)
	}
	if _, err := tx.Exec(ctx, `
		INSERT INTO greeting_request_outbox (
			event_id, aggregate_id, event_name, payload_json, occurred_at
		) VALUES ($1, $2, $3, $4, $5)`,
		commit.EventID, greeting.ID, commit.EventName, eventPayload, commit.OccurredAt,
	); err != nil {
		return fmt.Errorf("append greeting outbox: %w", err)
	}

	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit greeting command: %w", err)
	}
	committed = true
	return nil
}

func nullableJSON(value json.RawMessage) any {
	if len(value) == 0 || string(value) == "null" {
		return nil
	}
	return value
}

func (s *PgGreetingStore) ClaimPendingOutbox(
	ctx context.Context,
	ownerID string,
	lease time.Duration,
	limit int,
) ([]greetingrepo.GreetingOutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := s.pool.Query(ctx, `
		UPDATE greeting_request_outbox
		SET claim_owner = $1, claimed_at = NOW()
		WHERE event_id IN (
			SELECT event_id FROM greeting_request_outbox
			WHERE published_at IS NULL
			  AND (claim_owner IS NULL OR claimed_at < NOW() - $2::interval)
			ORDER BY occurred_at
			LIMIT $3
			FOR UPDATE SKIP LOCKED
		)
		RETURNING event_id, aggregate_id, event_name, payload_json, occurred_at`,
		ownerID, lease.String(), limit,
	)
	if err != nil {
		return nil, fmt.Errorf("claim greeting outbox: %w", err)
	}
	defer rows.Close()
	var events []greetingrepo.GreetingOutboxEvent
	for rows.Next() {
		var (
			event   greetingrepo.GreetingOutboxEvent
			payload []byte
		)
		if err := rows.Scan(&event.EventID, &event.AggregateID, &event.EventName, &payload, &event.OccurredAt); err != nil {
			return nil, fmt.Errorf("scan greeting outbox: %w", err)
		}
		if err := json.Unmarshal(payload, &event.Payload); err != nil {
			return nil, fmt.Errorf("decode greeting outbox payload: %w", err)
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

func (s *PgGreetingStore) MarkOutboxPublished(ctx context.Context, eventID, ownerID string) error {
	tag, err := s.pool.Exec(ctx, `
		UPDATE greeting_request_outbox
		SET published_at = NOW()
		WHERE event_id = $1 AND claim_owner = $2 AND published_at IS NULL`,
		eventID, ownerID,
	)
	if err != nil {
		return fmt.Errorf("mark greeting outbox published: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return greetingrepo.ErrGreetingOutboxClaimLost
	}
	return nil
}

func (s *PgGreetingStore) ReleaseOutboxClaim(ctx context.Context, eventID, ownerID string) error {
	if _, err := s.pool.Exec(ctx, `
		UPDATE greeting_request_outbox
		SET claim_owner = NULL, claimed_at = NULL
		WHERE event_id = $1 AND claim_owner = $2 AND published_at IS NULL`,
		eventID, ownerID,
	); err != nil {
		return fmt.Errorf("release greeting outbox claim: %w", err)
	}
	return nil
}

// CountRecentByRequester 统计 24h 窗口内该发起者创建的打招呼数（限流）。
func (s *PgGreetingStore) CountRecentByRequester(
	ctx context.Context,
	requesterPersonaID string,
	window time.Duration,
) (int64, error) {
	var count int64
	err := s.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM greeting_requests
		WHERE requester_persona_id = $1 AND created_at > NOW() - $2::interval`,
		requesterPersonaID, window.String(),
	).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("count recent greetings: %w", err)
	}
	return count, nil
}
