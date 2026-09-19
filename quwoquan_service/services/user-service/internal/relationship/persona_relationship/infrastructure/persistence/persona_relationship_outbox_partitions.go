package persistence

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relports "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/ports"
)

func (s *PgPersonaRelationshipStore) ClaimOutboxPartitions(
	ctx context.Context,
	consumer string,
	owner string,
	lease time.Duration,
	maxPartitions int,
) ([]relports.OutboxPartitionLease, error) {
	consumer = strings.TrimSpace(consumer)
	owner = strings.TrimSpace(owner)
	if consumer == "" || owner == "" {
		return nil, errors.New("persona relationship outbox consumer and owner are required")
	}
	if lease <= 0 {
		lease = time.Minute
	}
	if maxPartitions <= 0 || maxPartitions > relports.PersonaRelationshipOutboxPartitionCount {
		maxPartitions = relports.PersonaRelationshipOutboxPartitionCount
	}
	if _, err := s.pool.Exec(ctx, `
		INSERT INTO persona_relationship_outbox_checkpoints (consumer, partition_id)
		SELECT $1, partition_id
		FROM generate_series(0, $2 - 1) AS partition_id
		ON CONFLICT (consumer, partition_id) DO NOTHING`,
		consumer, relports.PersonaRelationshipOutboxPartitionCount,
	); err != nil {
		return nil, fmt.Errorf("ensure persona relationship outbox checkpoints: %w", err)
	}
	rows, err := s.pool.Query(ctx, `
		WITH candidates AS (
			SELECT consumer, partition_id
			FROM persona_relationship_outbox_checkpoints
			WHERE consumer = $1
			  AND (lease_until IS NULL OR lease_until <= NOW() OR lease_owner = $2)
			ORDER BY partition_id
			LIMIT $3
			FOR UPDATE SKIP LOCKED
		)
		UPDATE persona_relationship_outbox_checkpoints AS checkpoint
		SET lease_owner = $2,
			lease_until = NOW() + ($4 * INTERVAL '1 second'),
			lease_epoch = checkpoint.lease_epoch + 1,
			updated_at = NOW()
		FROM candidates
		WHERE checkpoint.consumer = candidates.consumer
		  AND checkpoint.partition_id = candidates.partition_id
		RETURNING checkpoint.partition_id, checkpoint.sequence,
			checkpoint.lease_epoch, checkpoint.lease_until`,
		consumer, owner, maxPartitions, lease.Seconds(),
	)
	if err != nil {
		return nil, fmt.Errorf("claim persona relationship outbox partitions: %w", err)
	}
	defer rows.Close()
	leases := make([]relports.OutboxPartitionLease, 0, maxPartitions)
	for rows.Next() {
		lease := relports.OutboxPartitionLease{Consumer: consumer, Owner: owner}
		if err := rows.Scan(
			&lease.PartitionID,
			&lease.Sequence,
			&lease.LeaseEpoch,
			&lease.LeaseUntil,
		); err != nil {
			return nil, fmt.Errorf("scan persona relationship outbox partition lease: %w", err)
		}
		leases = append(leases, lease)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship outbox partition leases: %w", err)
	}
	return leases, nil
}

func (s *PgPersonaRelationshipStore) ReadOutboxPartition(
	ctx context.Context,
	lease relports.OutboxPartitionLease,
	limit int,
) ([]relports.PartitionedOutboxEvent, error) {
	if limit <= 0 || limit > 200 {
		limit = 100
	}
	var leaseCurrent bool
	if err := s.pool.QueryRow(ctx, `
		SELECT EXISTS (
			SELECT 1 FROM persona_relationship_outbox_checkpoints
			WHERE consumer=$1 AND partition_id=$2 AND sequence=$3
			  AND lease_owner=$4 AND lease_epoch=$5 AND lease_until > NOW()
		)`, lease.Consumer, lease.PartitionID, lease.Sequence, lease.Owner, lease.LeaseEpoch,
	).Scan(&leaseCurrent); err != nil {
		return nil, fmt.Errorf("validate persona relationship outbox lease: %w", err)
	}
	if !leaseCurrent {
		return nil, fmt.Errorf("%w: partition %d epoch %d", relports.ErrOutboxLeaseLost, lease.PartitionID, lease.LeaseEpoch)
	}
	rows, err := s.pool.Query(ctx, `
		SELECT event_id, event_name, aggregate_id, aggregate_version,
			payload_json, partition_sequence
		FROM persona_relationship_outbox
		WHERE partition_id = $1 AND partition_sequence > $2
		ORDER BY partition_sequence
		LIMIT $3`, lease.PartitionID, lease.Sequence, limit)
	if err != nil {
		return nil, fmt.Errorf("read persona relationship outbox partition: %w", err)
	}
	defer rows.Close()
	events := make([]relports.PartitionedOutboxEvent, 0, limit)
	expected := lease.Sequence + 1
	for rows.Next() {
		var (
			event            relmodel.OutboxEvent
			aggregateID      string
			aggregateVersion int64
			payload          []byte
			sequence         int64
		)
		if err := rows.Scan(
			&event.EventID,
			&event.EventName,
			&aggregateID,
			&aggregateVersion,
			&payload,
			&sequence,
		); err != nil {
			return nil, fmt.Errorf("scan persona relationship partition event: %w", err)
		}
		if sequence != expected {
			return nil, fmt.Errorf(
				"persona relationship outbox partition %d has gap: got %d want %d",
				lease.PartitionID, sequence, expected,
			)
		}
		if err := json.Unmarshal(payload, &event.Payload); err != nil {
			return nil, fmt.Errorf("decode persona relationship partition event: %w", err)
		}
		if event.Payload.PairID != aggregateID || event.Payload.Version != aggregateVersion {
			return nil, errors.New("persona relationship outbox aggregate identity mismatch")
		}
		events = append(events, relports.PartitionedOutboxEvent{
			PartitionKey: aggregateID, PartitionID: lease.PartitionID,
			PartitionSequence: sequence, Event: event,
		})
		expected++
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona relationship partition events: %w", err)
	}
	return events, nil
}

func (s *PgPersonaRelationshipStore) AdvanceOutboxCheckpoint(
	ctx context.Context,
	lease relports.OutboxPartitionLease,
	event relports.PartitionedOutboxEvent,
) error {
	if event.PartitionID != lease.PartitionID ||
		event.PartitionSequence != lease.Sequence+1 {
		return fmt.Errorf("%w: non-contiguous sequence", relports.ErrOutboxLeaseLost)
	}
	tx, err := s.pool.BeginTx(ctx, pgx.TxOptions{})
	if err != nil {
		return fmt.Errorf("begin persona relationship checkpoint advance: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()
	command, err := tx.Exec(ctx, `
		UPDATE persona_relationship_outbox_checkpoints
		SET sequence = $1, updated_at = NOW()
		WHERE consumer = $2 AND partition_id = $3
		  AND sequence = $4 AND lease_owner = $5 AND lease_epoch = $6
		  AND lease_until > NOW()`,
		event.PartitionSequence, lease.Consumer, lease.PartitionID,
		lease.Sequence, lease.Owner, lease.LeaseEpoch,
	)
	if err != nil {
		return fmt.Errorf("advance persona relationship checkpoint: %w", err)
	}
	if command.RowsAffected() != 1 {
		return fmt.Errorf("%w: partition %d epoch %d", relports.ErrOutboxLeaseLost, lease.PartitionID, lease.LeaseEpoch)
	}
	command, err = tx.Exec(ctx, `
		UPDATE persona_relationship_outbox
		SET published_at = COALESCE(published_at, NOW())
		WHERE event_id = $1 AND partition_id = $2 AND partition_sequence = $3`,
		event.Event.EventID, event.PartitionID, event.PartitionSequence,
	)
	if err != nil {
		return fmt.Errorf("mark persona relationship partition event published: %w", err)
	}
	if command.RowsAffected() != 1 {
		return errors.New("persona relationship outbox event disappeared during checkpoint advance")
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("commit persona relationship checkpoint advance: %w", err)
	}
	return nil
}

var _ relports.PartitionedPersonaRelationshipOutbox = (*PgPersonaRelationshipStore)(nil)
