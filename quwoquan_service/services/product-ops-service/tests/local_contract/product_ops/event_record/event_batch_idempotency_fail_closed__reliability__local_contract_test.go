// 事件批次投递的可靠性契约：重复投递幂等去重、存储写入失败 fail-closed
// （不 MarkAccepted、不返回伪成功、不伪装重复批次）。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

// failingPutEventStore 模拟存储写入故障：PutEventBatch 恒失败且写入不可确认。
type failingPutEventStore struct {
	*telemetrypersistence.MemoryTelemetryStore
	putAttempts int
}

func (store *failingPutEventStore) PutEventBatch(
	_ context.Context,
	_ string,
	_ []application.EventRecord,
) error {
	store.putAttempts++
	return errors.New("logstore write failed")
}

func (store *failingPutEventStore) HasEventBatch(
	context.Context,
	string,
	int,
) (bool, error) {
	return false, nil
}

// recordingLedger 记录 MarkAccepted 调用：失败路径不得留下 accepted 台账。
type recordingLedger struct {
	inner        application.EventBatchLedger
	mu           sync.Mutex
	acceptedKeys []string
}

func (ledger *recordingLedger) Begin(
	ctx context.Context,
	batchKey string,
	count int,
) (application.BatchLedgerState, error) {
	return ledger.inner.Begin(ctx, batchKey, count)
}

func (ledger *recordingLedger) MarkAccepted(
	ctx context.Context,
	batchKey string,
	count int,
) error {
	ledger.mu.Lock()
	ledger.acceptedKeys = append(ledger.acceptedKeys, batchKey)
	ledger.mu.Unlock()
	return ledger.inner.MarkAccepted(ctx, batchKey, count)
}

func (ledger *recordingLedger) accepted() int {
	ledger.mu.Lock()
	defer ledger.mu.Unlock()
	return len(ledger.acceptedKeys)
}

func TestEventBatchReplayIsIdempotentNotDoubleCounted(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	now := time.Now().UTC().Add(-2 * time.Minute)
	events := []application.EventRecordInput{
		validEvent("page_open", "event", now),
		validEvent("page_return", "event", now.Add(time.Second)),
	}
	duration := 1200
	events[1].DurationMS = &duration
	batchKey := digestKey("reliability-idempotent-batch")

	first, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil || first.DuplicateBatch || first.AcceptedCount != 2 {
		t.Fatalf("first batch ack=%+v err=%v", first, err)
	}
	replay, err := service.ReportEventBatch(context.Background(), batchKey, events)
	if err != nil {
		t.Fatalf("replay batch: %v", err)
	}
	if !replay.DuplicateBatch || replay.AcceptedCount != 2 {
		t.Fatalf("replay must be deduplicated as duplicate batch, got %+v", replay)
	}
	confirmed, err := store.HasEventBatch(context.Background(), batchKey, len(events))
	if err != nil || !confirmed {
		t.Fatalf("batch must be confirmed exactly once, confirmed=%v err=%v", confirmed, err)
	}
}

func TestEventBatchStoreFailureFailsClosedWithoutFakeSuccess(t *testing.T) {
	memory := telemetrypersistence.NewMemoryTelemetryStore()
	store := &failingPutEventStore{MemoryTelemetryStore: memory}
	ledger := &recordingLedger{inner: memory}
	service := application.NewTelemetryService(store, ledger)
	now := time.Now().UTC().Add(-2 * time.Minute)
	events := []application.EventRecordInput{validEvent("page_open", "event", now)}

	ack, err := service.ReportEventBatch(
		context.Background(),
		digestKey("reliability-fail-closed-batch"),
		events,
	)
	if err == nil {
		t.Fatalf("store failure must fail closed; got ack=%+v", ack)
	}
	if ack.DuplicateBatch || ack.AcceptedCount != 0 {
		t.Fatalf("failed batch must not fabricate success or duplicate ack: %+v", ack)
	}
	if ledger.accepted() != 0 {
		t.Fatalf(
			"failed batch must not MarkAccepted; accepted keys=%d",
			ledger.accepted(),
		)
	}
	if store.putAttempts != 1 {
		t.Fatalf("put attempts=%d want=1", store.putAttempts)
	}
}
