// Package persistence 实现 CredentialBinding 对象专属 PostgreSQL Store。
package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
)

type PostgresStore struct {
	pool *pgxpool.Pool
}

func NewPostgresStore(pool *pgxpool.Pool) (*PostgresStore, error) {
	if pool == nil {
		return nil, errors.New("CredentialBinding PostgreSQL pool is required")
	}
	return &PostgresStore{pool: pool}, nil
}

var _ bindingports.AggregateStore = (*PostgresStore)(nil)

// Bind 依靠 credential_bindings 的两个唯一约束完成串行化：
// credential_type + credential_key 保证全局唯一，owner_id + credential_type
// 保证同账号每种类型只有一个 identity。ON CONFLICT 后读取权威行，只有同账号、
// 同 key 且仍 active 才是自然 no-op；revoked 行不会被更新或复活。
func (store *PostgresStore) Bind(
	ctx context.Context,
	change bindingmodel.ChangeSet,
) (bindingports.BindResult, error) {
	event, err := validateBindChange(change)
	if err != nil {
		return bindingports.BindResult{}, err
	}
	state := change.Aggregate.State()
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return bindingports.BindResult{}, fmt.Errorf(
			"begin CredentialBinding bind: %w",
			err,
		)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	tag, err := tx.Exec(ctx, `
INSERT INTO credential_bindings(
  id, owner_id, credential_type, credential_key, display_label,
  is_active, bound_at, last_used_at, version
) VALUES ($1,$2,$3,$4,NULLIF($5,''),true,$6,$7,$8)
ON CONFLICT DO NOTHING`,
		state.ID,
		state.OwnerID,
		state.CredentialType,
		state.CredentialKey,
		state.DisplayLabel,
		state.BoundAt,
		state.LastUsedAt,
		state.Version,
	)
	if err != nil {
		return bindingports.BindResult{}, fmt.Errorf(
			"insert CredentialBinding state: %w",
			err,
		)
	}
	if tag.RowsAffected() == 0 {
		existing, found, loadErr := loadByTypeAndKey(
			ctx,
			tx,
			state.CredentialType,
			state.CredentialKey,
		)
		if loadErr != nil {
			return bindingports.BindResult{}, loadErr
		}
		if found {
			existingState := existing.State()
			if existingState.OwnerID == state.OwnerID &&
				existingState.Status == bindingmodel.StatusActive {
				if err := tx.Commit(ctx); err != nil {
					return bindingports.BindResult{}, fmt.Errorf(
						"commit CredentialBinding no-op: %w",
						err,
					)
				}
				return bindingports.BindResult{
					Aggregate: existing,
					Replayed:  true,
				}, nil
			}
			return bindingports.BindResult{}, bindingports.ErrCredentialConflict
		}
		_, ownerTypeFound, loadErr := loadByOwnerAndType(
			ctx,
			tx,
			state.OwnerID,
			state.CredentialType,
		)
		if loadErr != nil {
			return bindingports.BindResult{}, loadErr
		}
		if ownerTypeFound {
			return bindingports.BindResult{}, bindingports.ErrCredentialConflict
		}
		_, idFound, loadErr := loadByID(ctx, tx, state.ID)
		if loadErr != nil {
			return bindingports.BindResult{}, loadErr
		}
		if idFound {
			return bindingports.BindResult{}, errors.New(
				"CredentialBinding aggregate identity collision",
			)
		}
		return bindingports.BindResult{}, errors.New(
			"CredentialBinding insert conflicted without a matching unique identity",
		)
	}
	if err := appendSecurityOutbox(ctx, tx, event); err != nil {
		return bindingports.BindResult{}, err
	}
	if err := tx.Commit(ctx); err != nil {
		return bindingports.BindResult{}, fmt.Errorf(
			"commit CredentialBinding bind: %w",
			err,
		)
	}
	return bindingports.BindResult{Aggregate: change.Aggregate}, nil
}

func (store *PostgresStore) LoadByOwnerAndType(
	ctx context.Context,
	ownerID string,
	credentialType bindingmodel.CredentialType,
) (bindingmodel.CredentialBinding, bool, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" || !credentialType.Valid() {
		return bindingmodel.CredentialBinding{}, false,
			bindingmodel.ErrInvalidCredentialBinding
	}
	return loadByOwnerAndType(ctx, store.pool, ownerID, credentialType)
}

func (store *PostgresStore) FindByTypeAndKey(
	ctx context.Context,
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) (bindingmodel.CredentialBinding, bool, error) {
	credentialKey = strings.TrimSpace(credentialKey)
	if !credentialType.Valid() || credentialKey == "" {
		return bindingmodel.CredentialBinding{}, false,
			bindingmodel.ErrInvalidCredentialBinding
	}
	return loadByTypeAndKey(
		ctx,
		store.pool,
		credentialType,
		credentialKey,
	)
}

func (store *PostgresStore) MarkUsed(
	ctx context.Context,
	aggregateID string,
	usedAt time.Time,
) error {
	aggregateID = strings.TrimSpace(aggregateID)
	if aggregateID == "" || usedAt.IsZero() {
		return bindingmodel.ErrInvalidCredentialBinding
	}
	tag, err := store.pool.Exec(ctx, `
UPDATE credential_bindings
SET last_used_at=$2
WHERE id=$1 AND is_active=true`, aggregateID, usedAt.UTC())
	if err != nil {
		return fmt.Errorf("mark CredentialBinding used: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return bindingports.ErrCredentialBindingNotFound
	}
	return nil
}

func (store *PostgresStore) ListByOwner(
	ctx context.Context,
	ownerID string,
) ([]bindingmodel.CredentialBinding, error) {
	ownerID = strings.TrimSpace(ownerID)
	if ownerID == "" {
		return nil, bindingmodel.ErrInvalidCredentialBinding
	}
	rows, err := store.pool.Query(ctx, `
SELECT `+credentialBindingSelectColumns+`
FROM credential_bindings
WHERE owner_id=$1
ORDER BY bound_at, id`, ownerID)
	if err != nil {
		return nil, fmt.Errorf("list CredentialBinding owner set: %w", err)
	}
	defer rows.Close()
	items := make([]bindingmodel.CredentialBinding, 0)
	for rows.Next() {
		item, found, scanErr := scanCredentialBinding(rows)
		if scanErr != nil {
			return nil, scanErr
		}
		if found {
			items = append(items, item)
		}
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate CredentialBinding owner set: %w", err)
	}
	return items, nil
}

// CommitRevoke 锁定 owner 的全部绑定行，在同一 PostgreSQL transaction 内
// 校验恢复不变量、执行内部 version CAS，并写入 CredentialRevoked outbox。
func (store *PostgresStore) CommitRevoke(
	ctx context.Context,
	expectedVersion int64,
	change bindingmodel.ChangeSet,
) error {
	event, err := validateRevokeChange(expectedVersion, change)
	if err != nil {
		return err
	}
	next := change.Aggregate.State()
	tx, err := store.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("begin CredentialBinding revoke: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	rows, err := tx.Query(ctx, `
SELECT `+credentialBindingSelectColumns+`
FROM credential_bindings
WHERE owner_id=$1
ORDER BY bound_at, id
FOR UPDATE`, next.OwnerID)
	if err != nil {
		return fmt.Errorf("lock CredentialBinding owner set: %w", err)
	}
	var (
		current              bindingmodel.CredentialBinding
		targetFound          bool
		remainingRecoverable int
	)
	for rows.Next() {
		candidate, found, scanErr := scanCredentialBinding(rows)
		if scanErr != nil {
			rows.Close()
			return scanErr
		}
		if !found {
			continue
		}
		state := candidate.State()
		if state.ID == next.ID {
			current = candidate
			targetFound = true
			continue
		}
		if state.Status == bindingmodel.StatusActive &&
			state.CredentialType.Recoverable() {
			remainingRecoverable++
		}
	}
	rowsErr := rows.Err()
	rows.Close()
	if rowsErr != nil {
		return fmt.Errorf("read locked CredentialBinding owner set: %w", rowsErr)
	}
	if !targetFound {
		return bindingports.ErrCredentialBindingNotFound
	}
	currentState := current.State()
	if currentState.Status != bindingmodel.StatusActive ||
		currentState.Version != expectedVersion {
		return bindingmodel.ErrVersionConflict
	}
	if !sameBindingIdentity(currentState, next) {
		return bindingmodel.ErrVersionConflict
	}
	if remainingRecoverable == 0 {
		return bindingports.ErrLastRecoverableCredential
	}

	tag, err := tx.Exec(ctx, `
UPDATE credential_bindings
SET is_active=false, version=$3
WHERE id=$1 AND version=$2 AND is_active=true`,
		next.ID,
		expectedVersion,
		next.Version,
	)
	if err != nil {
		return fmt.Errorf("update CredentialBinding revoke state: %w", err)
	}
	if tag.RowsAffected() != 1 {
		return bindingmodel.ErrVersionConflict
	}
	if err := appendSecurityOutbox(ctx, tx, event); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit CredentialBinding revoke: %w", err)
	}
	return nil
}

type credentialBindingQueryer interface {
	QueryRow(context.Context, string, ...any) pgx.Row
}

func loadByID(
	ctx context.Context,
	queryer credentialBindingQueryer,
	id string,
) (bindingmodel.CredentialBinding, bool, error) {
	return scanCredentialBinding(queryer.QueryRow(ctx, `
SELECT `+credentialBindingSelectColumns+`
FROM credential_bindings
WHERE id=$1`, id))
}

func loadByTypeAndKey(
	ctx context.Context,
	queryer credentialBindingQueryer,
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) (bindingmodel.CredentialBinding, bool, error) {
	return scanCredentialBinding(queryer.QueryRow(ctx, `
SELECT `+credentialBindingSelectColumns+`
FROM credential_bindings
WHERE credential_type=$1 AND credential_key=$2`,
		credentialType,
		credentialKey,
	))
}

func loadByOwnerAndType(
	ctx context.Context,
	queryer credentialBindingQueryer,
	ownerID string,
	credentialType bindingmodel.CredentialType,
) (bindingmodel.CredentialBinding, bool, error) {
	return scanCredentialBinding(queryer.QueryRow(ctx, `
SELECT `+credentialBindingSelectColumns+`
FROM credential_bindings
WHERE owner_id=$1 AND credential_type=$2
ORDER BY bound_at DESC, id DESC
LIMIT 1`,
		ownerID,
		credentialType,
	))
}

func validateBindChange(
	change bindingmodel.ChangeSet,
) (bindingmodel.Event, error) {
	if !change.Changed || len(change.Events) != 1 {
		return bindingmodel.Event{}, bindingmodel.ErrInvalidCredentialBinding
	}
	if err := change.Aggregate.Validate(); err != nil {
		return bindingmodel.Event{}, err
	}
	state := change.Aggregate.State()
	event := change.Events[0]
	if state.Status != bindingmodel.StatusActive ||
		state.Version != 1 ||
		!validSecurityEventID(event.ID) ||
		event.Type != bindingmodel.CredentialBoundEvent ||
		event.AggregateID != state.ID ||
		event.AggregateVersion != state.Version ||
		!event.OccurredAt.Equal(state.BoundAt) {
		return bindingmodel.Event{}, bindingmodel.ErrInvalidCredentialBinding
	}
	return event, nil
}

func validateRevokeChange(
	expectedVersion int64,
	change bindingmodel.ChangeSet,
) (bindingmodel.Event, error) {
	if expectedVersion < 1 || !change.Changed || len(change.Events) != 1 {
		return bindingmodel.Event{}, bindingmodel.ErrVersionConflict
	}
	if err := change.Aggregate.Validate(); err != nil {
		return bindingmodel.Event{}, err
	}
	state := change.Aggregate.State()
	event := change.Events[0]
	if state.Status != bindingmodel.StatusRevoked ||
		state.Version != expectedVersion+1 ||
		!validSecurityEventID(event.ID) ||
		event.Type != bindingmodel.CredentialRevokedEvent ||
		event.AggregateID != state.ID ||
		event.AggregateVersion != state.Version ||
		event.OccurredAt.IsZero() ||
		event.OccurredAt.Before(state.BoundAt) {
		return bindingmodel.Event{}, bindingmodel.ErrVersionConflict
	}
	return event, nil
}

func appendSecurityOutbox(
	ctx context.Context,
	tx pgx.Tx,
	event bindingmodel.Event,
) error {
	payload, err := json.Marshal(struct {
		ID string `json:"id"`
	}{ID: event.AggregateID})
	if err != nil {
		return fmt.Errorf("encode CredentialBinding security outbox: %w", err)
	}
	if _, err := tx.Exec(ctx, `
INSERT INTO credential_bindings_outbox(
  event_id, aggregate_id, aggregate_version, event_type, payload_json, occurred_at
) VALUES ($1,$2,$3,$4,$5,$6)`,
		event.ID,
		event.AggregateID,
		event.AggregateVersion,
		event.Type,
		payload,
		event.OccurredAt,
	); err != nil {
		return fmt.Errorf("append CredentialBinding security outbox: %w", err)
	}
	return nil
}

func sameBindingIdentity(left, right bindingmodel.State) bool {
	return left.ID == right.ID &&
		left.OwnerID == right.OwnerID &&
		left.CredentialType == right.CredentialType &&
		left.CredentialKey == right.CredentialKey &&
		left.DisplayLabel == right.DisplayLabel &&
		left.BoundAt.Equal(right.BoundAt) &&
		equalOptionalTime(left.LastUsedAt, right.LastUsedAt)
}

func equalOptionalTime(left, right *time.Time) bool {
	if left == nil || right == nil {
		return left == nil && right == nil
	}
	return left.Equal(*right)
}

func validSecurityEventID(value string) bool {
	return value != "" &&
		strings.TrimSpace(value) == value &&
		len(value) <= 64
}
