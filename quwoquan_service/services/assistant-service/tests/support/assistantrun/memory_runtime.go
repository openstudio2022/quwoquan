// Package assistantrun contains object-level typed in-memory doubles for
// local_contract tests. It is test-tree only and cannot enter production
// composition.
package assistantrun

import (
	"context"
	"sync"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

type MemoryRuntime struct {
	mu       sync.Mutex
	runs     map[string]runruntime.Run
	requests map[string]string
	events   map[string][]runruntime.JournalEvent
	receipts map[string]runruntime.CommandReceipt
	ready    []string
	claims   map[string]runruntime.WorkClaim
	fencing  int64
	now      func() time.Time
}

func NewMemoryRuntime() *MemoryRuntime {
	return NewMemoryRuntimeWithClock(time.Now)
}

func NewMemoryRuntimeWithClock(now func() time.Time) *MemoryRuntime {
	if now == nil {
		now = time.Now
	}
	return &MemoryRuntime{
		runs:     map[string]runruntime.Run{},
		requests: map[string]string{},
		events:   map[string][]runruntime.JournalEvent{},
		receipts: map[string]runruntime.CommandReceipt{},
		claims:   map[string]runruntime.WorkClaim{},
		now:      now,
	}
}

func (r *MemoryRuntime) Load(
	_ context.Context,
	runID string,
) (runruntime.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return run, nil
}

func (r *MemoryRuntime) LoadByRequest(
	_ context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	runID, ok := r.requests[requestKey(userID, sessionID, clientRequestID)]
	if !ok {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return r.runs[runID], nil
}

func (r *MemoryRuntime) LoadCommandReceipt(
	_ context.Context,
	runID string,
	commandID string,
) (runruntime.CommandReceipt, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	receipt, ok := r.receipts[runID+"\x00"+commandID]
	if !ok {
		return runruntime.CommandReceipt{}, runruntime.ErrRunNotFound
	}
	return receipt, nil
}

func (r *MemoryRuntime) Commit(
	_ context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.commitLocked(expectedRevision, run, events, receipt)
}

func (r *MemoryRuntime) CommitClaim(
	_ context.Context,
	claim runruntime.WorkClaim,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, ok := r.claims[claim.RunID]
	if !ok || claim.RunID != run.RunID || current.WorkerID != claim.WorkerID ||
		current.FencingToken != claim.FencingToken ||
		!current.ExpiresAt.After(r.now().UTC()) {
		return runruntime.ErrExecutionFenced
	}
	return r.commitLocked(expectedRevision, run, events, receipt)
}

func (r *MemoryRuntime) commitLocked(
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	current, found := r.runs[run.RunID]
	if found {
		if current.Revision != expectedRevision {
			return runruntime.ErrRevisionConflict
		}
	} else if expectedRevision != 0 {
		return runruntime.ErrRevisionConflict
	}
	key := requestKey(run.UserID, run.SessionID, run.ClientRequestID)
	if existing, ok := r.requests[key]; ok && existing != run.RunID {
		return runruntime.ErrRevisionConflict
	}
	journal := r.events[run.RunID]
	lastSequence := int64(len(journal))
	for _, event := range events {
		if event.Sequence != lastSequence+1 {
			return runruntime.ErrRevisionConflict
		}
		journal = append(journal, event)
		lastSequence = event.Sequence
	}
	r.runs[run.RunID] = run
	r.requests[key] = run.RunID
	r.events[run.RunID] = journal
	if receipt != nil {
		receiptKey := receipt.RunID + "\x00" + receipt.CommandID
		if _, exists := r.receipts[receiptKey]; exists {
			return runruntime.ErrRevisionConflict
		}
		r.receipts[receiptKey] = *receipt
	}
	if queueRunnable(run.State.WireName()) {
		r.enqueueLocked(run.RunID)
	} else {
		r.removeReadyLocked(run.RunID)
		delete(r.claims, run.RunID)
	}
	return nil
}

func (r *MemoryRuntime) EventsAfter(
	_ context.Context,
	runID string,
	afterSequence int64,
	limit int,
) ([]runruntime.JournalEvent, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if _, ok := r.runs[runID]; !ok {
		return nil, runruntime.ErrRunNotFound
	}
	result := make([]runruntime.JournalEvent, 0, limit)
	for _, event := range r.events[runID] {
		if event.Sequence <= afterSequence {
			continue
		}
		result = append(result, event)
		if len(result) == limit {
			break
		}
	}
	return result, nil
}

func (r *MemoryRuntime) LatestSequence(
	ctx context.Context,
	runID string,
) (int64, error) {
	run, err := r.Load(ctx, runID)
	return run.JournalSequence, err
}

func (r *MemoryRuntime) ClaimNext(
	_ context.Context,
	workerID string,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if len(r.ready) == 0 {
		now := r.now().UTC()
		for runID, claim := range r.claims {
			if !claim.ExpiresAt.After(now) {
				r.ready = append(r.ready, runID)
				break
			}
		}
		if len(r.ready) == 0 {
			return runruntime.WorkClaim{}, runruntime.ErrNoWork
		}
	}
	runID := r.ready[0]
	r.ready = r.ready[1:]
	r.fencing++
	now := r.now().UTC()
	claim := runruntime.WorkClaim{
		RunID:        runID,
		WorkerID:     workerID,
		FencingToken: r.fencing,
		ClaimedAt:    now,
		ExpiresAt:    now.Add(ttl),
	}
	r.claims[runID] = claim
	return claim, nil
}

func (r *MemoryRuntime) HeartbeatClaim(
	_ context.Context,
	claim runruntime.WorkClaim,
	ttl time.Duration,
) (runruntime.WorkClaim, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, ok := r.claims[claim.RunID]
	if !ok || current.WorkerID != claim.WorkerID ||
		current.FencingToken != claim.FencingToken ||
		!current.ExpiresAt.After(r.now().UTC()) {
		return runruntime.WorkClaim{}, runruntime.ErrLeaseConflict
	}
	current.ExpiresAt = r.now().UTC().Add(ttl)
	r.claims[claim.RunID] = current
	return current, nil
}

func (r *MemoryRuntime) CompleteClaim(
	_ context.Context,
	claim runruntime.WorkClaim,
	reschedule bool,
	_ time.Time,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, ok := r.claims[claim.RunID]
	if !ok || current.WorkerID != claim.WorkerID ||
		current.FencingToken != claim.FencingToken ||
		!current.ExpiresAt.After(r.now().UTC()) {
		return runruntime.ErrLeaseConflict
	}
	delete(r.claims, claim.RunID)
	if reschedule {
		r.enqueueLocked(claim.RunID)
	}
	return nil
}

func (r *MemoryRuntime) enqueueLocked(runID string) {
	if r.claims[runID].RunID != "" {
		return
	}
	for _, ready := range r.ready {
		if ready == runID {
			return
		}
	}
	r.ready = append(r.ready, runID)
}

func (r *MemoryRuntime) removeReadyLocked(runID string) {
	for index, ready := range r.ready {
		if ready == runID {
			r.ready = append(r.ready[:index], r.ready[index+1:]...)
			return
		}
	}
}

func requestKey(userID, sessionID, clientRequestID string) string {
	return userID + "\x00" + sessionID + "\x00" + clientRequestID
}

func queueRunnable(state string) bool {
	switch state {
	case "completed", "failed", "cancelled", "paused",
		"waiting_user", "waiting_approval", "waiting_external":
		return false
	default:
		return true
	}
}

var (
	_ runruntime.WorkerRepository = (*MemoryRuntime)(nil)
	_ runruntime.WorkQueue        = (*MemoryRuntime)(nil)
)
