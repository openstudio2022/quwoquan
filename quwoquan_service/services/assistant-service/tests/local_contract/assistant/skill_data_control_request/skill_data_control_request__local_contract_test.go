// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-003
package local_contract

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
)

type dataControlClock struct {
	mu  sync.Mutex
	now time.Time
}

func (clock *dataControlClock) Now() time.Time {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	return clock.now
}

func (clock *dataControlClock) Advance(duration time.Duration) time.Time {
	clock.mu.Lock()
	defer clock.mu.Unlock()
	clock.now = clock.now.Add(duration)
	return clock.now
}

type dataControlReceipt struct {
	digest string
}

type dataControlStoreStub struct {
	mu             sync.Mutex
	request        model.Request
	receipts       map[string]dataControlReceipt
	heartbeatCount int
}

func newDataControlStoreStub() *dataControlStoreStub {
	return &dataControlStoreStub{receipts: map[string]dataControlReceipt{}}
}

func (store *dataControlStoreStub) Create(
	_ context.Context,
	command model.CreateCommand,
) (model.MutationResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, ok := store.receipts[command.IdempotencyKey]; ok {
		if receipt.digest != command.RequestDigest {
			return model.MutationResult{}, model.ErrIdempotencyConflict
		}
		return model.MutationResult{Request: store.request, Replayed: true}, nil
	}
	store.request = command.Request
	store.receipts[command.IdempotencyKey] = dataControlReceipt{digest: command.RequestDigest}
	return model.MutationResult{Request: store.request}, nil
}

func (store *dataControlStoreStub) Confirm(
	_ context.Context,
	command model.ConfirmCommand,
) (model.MutationResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, ok := store.receipts[command.IdempotencyKey]; ok {
		if receipt.digest != command.RequestDigest {
			return model.MutationResult{}, model.ErrIdempotencyConflict
		}
		return model.MutationResult{Request: store.request, Replayed: true}, nil
	}
	if store.request.AccountID != command.AccountID ||
		store.request.RequestID != command.RequestID {
		return model.MutationResult{}, model.ErrNotFound
	}
	if store.request.Revision != command.ExpectedRevision ||
		(store.request.Status != model.StatusPendingConfirmation &&
			store.request.Status != model.StatusFailed) {
		return model.MutationResult{}, model.ErrRevisionConflict
	}
	store.request.Revision++
	store.request.UpdatedAt = command.OccurredAt.UTC()
	store.request.LeaseOwner = ""
	store.request.LeaseExpiresAt = nil
	store.request.LeaseHeartbeatAt = nil
	if command.Confirmed {
		store.request.Status = model.StatusExecuting
		confirmedAt := command.OccurredAt.UTC()
		store.request.ConfirmedAt = &confirmedAt
		store.request.CompletedAt = nil
		store.request.FailedAction = ""
		store.request.FailureCode = ""
	} else {
		store.request.Status = model.StatusCancelled
		completedAt := command.OccurredAt.UTC()
		store.request.CompletedAt = &completedAt
	}
	store.receipts[command.IdempotencyKey] = dataControlReceipt{digest: command.RequestDigest}
	return model.MutationResult{Request: store.request}, nil
}

func (store *dataControlStoreStub) Get(
	_ context.Context,
	accountID string,
	requestID string,
) (model.Request, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.request.AccountID != accountID || store.request.RequestID != requestID {
		return model.Request{}, model.ErrNotFound
	}
	return store.request, nil
}

func (store *dataControlStoreStub) ClaimNextExecution(
	_ context.Context,
	workerID string,
	now time.Time,
	leaseTTL time.Duration,
) (model.ExecutionClaim, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.request.Status != model.StatusExecuting ||
		(store.request.LeaseOwner != "" && store.request.LeaseExpiresAt != nil &&
			store.request.LeaseExpiresAt.After(now)) {
		return model.ExecutionClaim{}, false, nil
	}
	heartbeatAt := now.UTC()
	expiresAt := heartbeatAt.Add(leaseTTL)
	store.request.LeaseOwner = workerID
	store.request.LeaseToken++
	store.request.LeaseHeartbeatAt = &heartbeatAt
	store.request.LeaseExpiresAt = &expiresAt
	fence, err := model.NewExecutionFence(store.request)
	if err != nil {
		return model.ExecutionClaim{}, false, err
	}
	return model.ExecutionClaim{Request: store.request, Fence: fence}, true, nil
}

func (store *dataControlStoreStub) HeartbeatExecution(
	_ context.Context,
	fence model.ExecutionFence,
	now time.Time,
	leaseTTL time.Duration,
) (model.ExecutionFence, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if !store.ownsFence(fence, now) {
		return model.ExecutionFence{}, model.ErrRevisionConflict
	}
	heartbeatAt := now.UTC()
	expiresAt := heartbeatAt.Add(leaseTTL)
	store.request.LeaseHeartbeatAt = &heartbeatAt
	store.request.LeaseExpiresAt = &expiresAt
	store.heartbeatCount++
	return model.NewExecutionFence(store.request)
}

func (store *dataControlStoreStub) MarkActionCompleted(
	_ context.Context,
	fence model.ExecutionFence,
	action string,
	revision int64,
	at time.Time,
) (model.Request, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.request.Revision != revision || !store.ownsFence(fence, at) {
		return model.Request{}, model.ErrRevisionConflict
	}
	if !store.request.HasCompleted(action) {
		store.request.CompletedActions = append(store.request.CompletedActions, action)
		store.request.Revision++
		store.request.UpdatedAt = at.UTC()
	}
	return store.request, nil
}

func (store *dataControlStoreStub) MarkCompleted(
	_ context.Context,
	fence model.ExecutionFence,
	revision int64,
	at time.Time,
) (model.Request, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.request.Revision != revision || !store.ownsFence(fence, at) ||
		len(store.request.CompletedActions) != len(store.request.RequestedActions) {
		return model.Request{}, model.ErrRevisionConflict
	}
	store.request.Status = model.StatusCompleted
	store.request.Revision++
	store.request.UpdatedAt = at.UTC()
	completedAt := at.UTC()
	store.request.CompletedAt = &completedAt
	store.clearLease()
	return store.request, nil
}

func (store *dataControlStoreStub) MarkFailed(
	_ context.Context,
	fence model.ExecutionFence,
	action string,
	code string,
	revision int64,
	at time.Time,
) (model.Request, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.request.Revision != revision || !store.ownsFence(fence, at) {
		return model.Request{}, model.ErrRevisionConflict
	}
	store.request.Status = model.StatusFailed
	store.request.FailedAction = action
	store.request.FailureCode = code
	store.request.Revision++
	store.request.UpdatedAt = at.UTC()
	store.clearLease()
	return store.request, nil
}

func (store *dataControlStoreStub) ListSkillDataControlActivities(
	context.Context,
	string,
	string,
	int,
) ([]model.ActivityEvent, error) {
	return nil, nil
}

func (store *dataControlStoreStub) ownsFence(
	fence model.ExecutionFence,
	now time.Time,
) bool {
	return store.request.Status == model.StatusExecuting &&
		store.request.AccountID == fence.AccountID &&
		store.request.RequestID == fence.RequestID &&
		store.request.LeaseOwner == fence.WorkerID &&
		store.request.LeaseToken == fence.Token &&
		store.request.LeaseExpiresAt != nil &&
		store.request.LeaseExpiresAt.After(now.UTC())
}

func (store *dataControlStoreStub) clearLease() {
	store.request.LeaseOwner = ""
	store.request.LeaseExpiresAt = nil
	store.request.LeaseHeartbeatAt = nil
}

func (store *dataControlStoreStub) heartbeats() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.heartbeatCount
}

type dataControlExecutorStub struct {
	mu         sync.Mutex
	calls      []string
	failAction string
}

type blockingDataControlExecutor struct {
	started chan struct{}
	release chan struct{}
}

func TestSkillDataControlActionClosureRejectsUnknownAndDuplicateValues(t *testing.T) {
	t.Parallel()
	for name, actions := range map[string][]string{
		"unknown":   {"delete_everything"},
		"duplicate": {model.ActionRevokeConsent, model.ActionRevokeConsent},
		"empty":     {},
	} {
		name, actions := name, actions
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if _, err := model.NormalizeActions(actions); !errors.Is(err, model.ErrInvalidArgument) {
				t.Fatalf("NormalizeActions(%v) error=%v, want invalid argument", actions, err)
			}
		})
	}
	normalized, err := model.NormalizeActions([]string{
		model.ActionRevokeConsent,
		model.ActionHideActivityHistory,
		model.ActionArchiveSubscriptions,
	})
	if err != nil {
		t.Fatalf("NormalizeActions(canonical) error=%v", err)
	}
	want := []string{
		model.ActionArchiveSubscriptions,
		model.ActionHideActivityHistory,
		model.ActionRevokeConsent,
	}
	for index := range want {
		if normalized[index] != want[index] {
			t.Fatalf("NormalizeActions(canonical)=%v, want %v", normalized, want)
		}
	}
}

func (executor *blockingDataControlExecutor) ExecuteSkillDataControlAction(
	ctx context.Context,
	_ model.Request,
	_ string,
) error {
	close(executor.started)
	select {
	case <-executor.release:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (executor *dataControlExecutorStub) ExecuteSkillDataControlAction(
	_ context.Context,
	_ model.Request,
	action string,
) error {
	executor.mu.Lock()
	defer executor.mu.Unlock()
	executor.calls = append(executor.calls, action)
	if action == executor.failAction {
		return errors.New("owner unavailable")
	}
	return nil
}

func TestSkillDataControlConfirmsBeforeDurableWorkerExecutesExactlyOnce(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	clock := &dataControlClock{now: time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)}
	store := newDataControlStoreStub()
	executor := &dataControlExecutorStub{}
	service := application.NewService(
		store,
		clock.Now,
		func() string { return "control-request-1" },
	)
	worker, err := application.NewWorker(
		store, executor, "worker-a", time.Second, 3*time.Second, clock.Now,
	)
	if err != nil {
		t.Fatalf("NewWorker() error=%v", err)
	}
	created, err := service.Create(
		ctx,
		"account-a",
		"travel_companion",
		[]string{model.ActionRevokeConsent, model.ActionArchiveSubscriptions},
		"create-control-1",
	)
	if err != nil || created.Request.Status != model.StatusPendingConfirmation {
		t.Fatalf("Create()=%+v error=%v", created, err)
	}
	confirmed, err := service.Confirm(
		ctx,
		"account-a",
		created.Request.RequestID,
		created.Request.Revision,
		true,
		"confirm-control-1",
	)
	if err != nil || confirmed.Request.Status != model.StatusExecuting {
		t.Fatalf("Confirm()=%+v error=%v", confirmed, err)
	}
	if len(executor.calls) != 0 {
		t.Fatalf("HTTP confirmation executed owner actions: %v", executor.calls)
	}
	processed, err := worker.RunOnce(ctx)
	if err != nil || !processed {
		t.Fatalf("RunOnce() processed=%v error=%v", processed, err)
	}
	completed, err := service.Get(ctx, "account-a", created.Request.RequestID)
	if err != nil || completed.Status != model.StatusCompleted ||
		len(completed.CompletedActions) != 2 {
		t.Fatalf("Get(completed)=%+v error=%v", completed, err)
	}
	if len(executor.calls) != 2 ||
		executor.calls[0] != model.ActionArchiveSubscriptions ||
		executor.calls[1] != model.ActionRevokeConsent {
		t.Fatalf("actions=%v", executor.calls)
	}
	replayed, err := service.Confirm(
		ctx,
		"account-a",
		created.Request.RequestID,
		created.Request.Revision,
		true,
		"confirm-control-1",
	)
	if err != nil || !replayed.Replayed || replayed.Request.Status != model.StatusCompleted {
		t.Fatalf("Confirm(replay)=%+v error=%v", replayed, err)
	}
	if len(executor.calls) != 2 {
		t.Fatalf("idempotent replay repeated owner actions: %v", executor.calls)
	}
}

func TestSkillDataControlExpiredLeaseResumesOnlyIncompleteActionsAndFencesOldWorker(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	clock := &dataControlClock{now: time.Date(2026, 8, 4, 10, 0, 0, 0, time.UTC)}
	store := newDataControlStoreStub()
	service := application.NewService(
		store,
		clock.Now,
		func() string { return "control-request-2" },
	)
	created, err := service.Create(
		ctx,
		"account-a",
		"travel_companion",
		[]string{model.ActionRevokeConsent, model.ActionArchiveSubscriptions},
		"create-control-2",
	)
	if err != nil {
		t.Fatalf("Create() error=%v", err)
	}
	executing, err := service.Confirm(
		ctx,
		"account-a",
		created.Request.RequestID,
		created.Request.Revision,
		true,
		"confirm-control-2",
	)
	if err != nil {
		t.Fatalf("Confirm() error=%v", err)
	}
	claimA, found, err := store.ClaimNextExecution(
		ctx, "worker-a", clock.Now(), 3*time.Second,
	)
	if err != nil || !found {
		t.Fatalf("ClaimNextExecution(worker-a) found=%v error=%v", found, err)
	}
	partial, err := store.MarkActionCompleted(
		ctx,
		claimA.Fence,
		model.ActionArchiveSubscriptions,
		executing.Request.Revision,
		clock.Now(),
	)
	if err != nil {
		t.Fatalf("MarkActionCompleted() error=%v", err)
	}
	clock.Advance(4 * time.Second)
	claimB, found, err := store.ClaimNextExecution(
		ctx, "worker-b", clock.Now(), 3*time.Second,
	)
	if err != nil || !found || claimB.Fence.Token <= claimA.Fence.Token {
		t.Fatalf("ClaimNextExecution(worker-b)=%+v found=%v error=%v", claimB, found, err)
	}
	if _, err := store.MarkActionCompleted(
		ctx,
		claimA.Fence,
		model.ActionRevokeConsent,
		partial.Revision,
		clock.Now(),
	); !errors.Is(err, model.ErrRevisionConflict) {
		t.Fatalf("expired fence MarkActionCompleted() error=%v", err)
	}
	// Release worker-b's lease by expiry so the real recovery worker can win.
	clock.Advance(4 * time.Second)
	executor := &dataControlExecutorStub{}
	worker, err := application.NewWorker(
		store, executor, "worker-c", time.Second, 3*time.Second, clock.Now,
	)
	if err != nil {
		t.Fatalf("NewWorker() error=%v", err)
	}
	processed, err := worker.RunOnce(ctx)
	if err != nil || !processed {
		t.Fatalf("RunOnce(recovery) processed=%v error=%v", processed, err)
	}
	if len(executor.calls) != 1 || executor.calls[0] != model.ActionRevokeConsent {
		t.Fatalf("recovery repeated completed actions: %v", executor.calls)
	}
	completed, err := service.Get(ctx, "account-a", created.Request.RequestID)
	if err != nil || completed.Status != model.StatusCompleted {
		t.Fatalf("Get(completed)=%+v error=%v", completed, err)
	}
}

func TestSkillDataControlConcurrentClaimHasSingleWinnerAndHeartbeatExtendsLease(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	clock := &dataControlClock{now: time.Date(2026, 8, 4, 11, 0, 0, 0, time.UTC)}
	store := newDataControlStoreStub()
	service := application.NewService(
		store,
		clock.Now,
		func() string { return "control-request-3" },
	)
	created, err := service.Create(
		ctx,
		"account-a",
		"travel_companion",
		[]string{model.ActionHideActivityHistory},
		"create-control-3",
	)
	if err != nil {
		t.Fatalf("Create() error=%v", err)
	}
	if _, err := service.Confirm(
		ctx,
		"account-a",
		created.Request.RequestID,
		created.Request.Revision,
		true,
		"confirm-control-3",
	); err != nil {
		t.Fatalf("Confirm() error=%v", err)
	}

	type claimResult struct {
		claim model.ExecutionClaim
		found bool
		err   error
	}
	results := make(chan claimResult, 2)
	for _, workerID := range []string{"worker-a", "worker-b"} {
		workerID := workerID
		go func() {
			claim, found, claimErr := store.ClaimNextExecution(
				ctx, workerID, clock.Now(), 3*time.Second,
			)
			results <- claimResult{claim: claim, found: found, err: claimErr}
		}()
	}
	winners := []model.ExecutionClaim{}
	for range 2 {
		result := <-results
		if result.err != nil {
			t.Fatalf("concurrent claim error=%v", result.err)
		}
		if result.found {
			winners = append(winners, result.claim)
		}
	}
	if len(winners) != 1 {
		t.Fatalf("concurrent winners=%d, want 1", len(winners))
	}
	originalExpiry := winners[0].Fence.LeaseExpiresAt
	clock.Advance(time.Second)
	heartbeat, err := store.HeartbeatExecution(
		ctx,
		winners[0].Fence,
		clock.Now(),
		3*time.Second,
	)
	if err != nil || !heartbeat.LeaseExpiresAt.After(originalExpiry) {
		t.Fatalf("HeartbeatExecution()=%+v error=%v", heartbeat, err)
	}
	clock.Advance(2500 * time.Millisecond)
	if _, found, err := store.ClaimNextExecution(
		ctx, "worker-c", clock.Now(), 3*time.Second,
	); err != nil || found {
		t.Fatalf("claim before heartbeat expiry found=%v error=%v", found, err)
	}
}

func TestSkillDataControlWorkerHeartbeatsDuringLongOwnerAction(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	store := newDataControlStoreStub()
	service := application.NewService(
		store,
		time.Now,
		func() string { return "control-request-heartbeat" },
	)
	created, err := service.Create(
		ctx,
		"account-a",
		"travel_companion",
		[]string{model.ActionHideActivityHistory},
		"create-control-heartbeat",
	)
	if err != nil {
		t.Fatalf("Create() error=%v", err)
	}
	if _, err := service.Confirm(
		ctx,
		"account-a",
		created.Request.RequestID,
		created.Request.Revision,
		true,
		"confirm-control-heartbeat",
	); err != nil {
		t.Fatalf("Confirm() error=%v", err)
	}
	executor := &blockingDataControlExecutor{
		started: make(chan struct{}),
		release: make(chan struct{}),
	}
	worker, err := application.NewWorker(
		store, executor, "worker-heartbeat", 10*time.Millisecond, 150*time.Millisecond, time.Now,
	)
	if err != nil {
		t.Fatalf("NewWorker() error=%v", err)
	}
	result := make(chan error, 1)
	go func() {
		_, runErr := worker.RunOnce(ctx)
		result <- runErr
	}()
	select {
	case <-executor.started:
	case <-time.After(time.Second):
		t.Fatal("owner action did not start")
	}
	deadline := time.Now().Add(time.Second)
	for store.heartbeats() == 0 && time.Now().Before(deadline) {
		time.Sleep(10 * time.Millisecond)
	}
	if store.heartbeats() == 0 {
		t.Fatal("worker did not heartbeat during long owner action")
	}
	close(executor.release)
	select {
	case err := <-result:
		if err != nil {
			t.Fatalf("RunOnce() error=%v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("worker did not finish after owner action completed")
	}
}
