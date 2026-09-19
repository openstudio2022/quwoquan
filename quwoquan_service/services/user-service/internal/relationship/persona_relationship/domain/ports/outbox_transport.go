package ports

import (
	"context"
	"encoding/hex"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

const PersonaRelationshipOutboxPartitionCount = 32

var ErrOutboxLeaseLost = errors.New("persona relationship outbox partition lease lost")

// OutboxPartitionLease fences one consumer's progress in one fixed partition.
// Sequence is the last continuously acknowledged source sequence.
type OutboxPartitionLease struct {
	Consumer    string
	Owner       string
	PartitionID int
	Sequence    int64
	LeaseEpoch  int64
	LeaseUntil  time.Time
}

// PartitionedOutboxEvent keeps transport ordering separate from aggregate
// version. EventID remains the stable downstream dedupe identity.
type PartitionedOutboxEvent struct {
	PartitionKey      string
	PartitionID       int
	PartitionSequence int64
	Event             model.OutboxEvent
}

// PartitionedPersonaRelationshipOutbox is the relay/checkpoint authority.
// A worker may only advance the exact next sequence while its lease epoch is
// current; gaps and failed events leave that partition's checkpoint unchanged.
type PartitionedPersonaRelationshipOutbox interface {
	ClaimOutboxPartitions(
		ctx context.Context,
		consumer string,
		owner string,
		lease time.Duration,
		maxPartitions int,
	) ([]OutboxPartitionLease, error)
	ReadOutboxPartition(
		ctx context.Context,
		lease OutboxPartitionLease,
		limit int,
	) ([]PartitionedOutboxEvent, error)
	AdvanceOutboxCheckpoint(
		ctx context.Context,
		lease OutboxPartitionLease,
		event PartitionedOutboxEvent,
	) error
}

// OutboxPartitionForKey is shared by storage and transport adapters. The hash
// is independent of process seed and remains stable across restarts/languages.
func OutboxPartitionForKey(key string) int {
	key = strings.TrimSpace(key)
	if len(key) < 8 {
		return -1
	}
	prefix, err := hex.DecodeString(key[:8])
	if err != nil || len(prefix) != 4 {
		return -1
	}
	value := uint32(prefix[0])<<24 | uint32(prefix[1])<<16 | uint32(prefix[2])<<8 | uint32(prefix[3])
	return int(value % PersonaRelationshipOutboxPartitionCount)
}

type outboxEnvelopeContextKey struct{}

func WithOutboxEnvelope(ctx context.Context, event PartitionedOutboxEvent) context.Context {
	return context.WithValue(ctx, outboxEnvelopeContextKey{}, event)
}

func OutboxEnvelopeFromContext(ctx context.Context) (PartitionedOutboxEvent, bool) {
	value, ok := ctx.Value(outboxEnvelopeContextKey{}).(PartitionedOutboxEvent)
	return value, ok
}
