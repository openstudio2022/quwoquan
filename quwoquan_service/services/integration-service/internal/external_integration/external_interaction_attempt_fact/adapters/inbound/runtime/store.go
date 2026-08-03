package runtimeadapter

import (
	"context"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/domain"
)

// Delegate 是 ExternalInteraction composition root 提供的任务存储。RuntimeStore
// 只接管 attempt 事实入口，其余任务能力原样提升给聚合应用层。
type Delegate interface {
	reliabletask.Store
	reliabletask.ProviderAttemptResultOutboxStore
	reliabletask.IdempotentDLQRecoveryStore
	reliabletask.RetentionCleanupStore
	reliabletask.MetricsStore
	ListDeadTasks(context.Context, []string, int) ([]reliabletask.DeadTaskRecord, error)
	FindLatestTaskOutboxByAggregateID(context.Context, string) (reliabletask.TaskOutboxRecord, bool, error)
}

type RuntimeStore struct {
	Delegate
}

func NewRuntimeStore(delegate Delegate) *RuntimeStore {
	return &RuntimeStore{Delegate: delegate}
}

func (store *RuntimeStore) RecordProviderAttempt(
	ctx context.Context,
	record reliabletask.ProviderAttemptRecord,
) (reliabletask.ProviderAttemptRecord, error) {
	if _, err := canonicalFact(record); err != nil {
		return reliabletask.ProviderAttemptRecord{}, err
	}
	return store.Delegate.RecordProviderAttempt(ctx, record)
}

func (store *RuntimeStore) RecordProviderAttemptWithResultOutbox(
	ctx context.Context,
	record reliabletask.ProviderAttemptRecord,
) (reliabletask.ProviderAttemptRecord, error) {
	if _, err := canonicalFact(record); err != nil {
		return reliabletask.ProviderAttemptRecord{}, err
	}
	return store.Delegate.RecordProviderAttemptWithResultOutbox(ctx, record)
}

func canonicalFact(record reliabletask.ProviderAttemptRecord) (domain.Fact, error) {
	return domain.NewFact(domain.Fact{
		AttemptID:             record.AttemptID,
		RequestID:             record.RequestID,
		TaskID:                record.TaskID,
		SubjectDigest:         record.SubjectDigest,
		Operation:             record.Operation,
		Provider:              record.Provider,
		ProviderRequestID:     record.ProviderRequestID,
		ProviderRequestDigest: record.ProviderRequestDigest,
		MaskedRecipient:       record.MaskedRecipient,
		LatencyMS:             record.LatencyMs,
		Status:                record.Status,
		NormalizedError:       record.NormalizedError,
		Retryable:             record.Retryable,
		RecoveryAction:        record.RecoveryAction,
		Attributes:            record.Attributes,
		CreatedAt:             record.CreatedAt,
	})
}
