package local_contract

import (
	"context"
	"encoding/json"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/application"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

func TestRingTimeoutSweeperFacetUsesNamedCutoffsAndMutationPipeline(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 20, 13, 0, 0, 0, time.UTC)
	firstStore := newSweeperCallStore(ringingSession(
		now.Add(-30*time.Second),
		model.MaxParticipants1v1,
	))
	first := newSweeperOrchestrator(firstStore, now)

	swept, err := first.SweepRingTimeouts(context.Background())
	if err != nil {
		t.Fatalf("SweepRingTimeouts() error = %v", err)
	}
	if swept != 1 {
		t.Fatalf("SweepRingTimeouts() = %d, want 1", swept)
	}

	firstStore.mu.Lock()
	if !firstStore.oneToOneCutoff.Equal(now.Add(-30 * time.Second)) {
		t.Fatalf("one-to-one cutoff = %v", firstStore.oneToOneCutoff)
	}
	if !firstStore.groupCutoff.Equal(now.Add(-60 * time.Second)) {
		t.Fatalf("group cutoff = %v", firstStore.groupCutoff)
	}
	if firstStore.findByIDCalls != 1 {
		t.Fatalf("authoritative reload count = %d, want 1", firstStore.findByIDCalls)
	}
	if firstStore.findReceiptCalls == 0 {
		t.Fatal("system command bypassed receipt replay lookup")
	}
	if len(firstStore.commits) != 1 {
		t.Fatalf("commit count = %d, want 1", len(firstStore.commits))
	}
	commit := firstStore.commits[0]
	firstStore.mu.Unlock()

	if commit.CommandName != "RingTimeout" {
		t.Fatalf("command name = %q, want RingTimeout", commit.CommandName)
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" {
		t.Fatal("system command idempotency key is empty")
	}
	if len(commit.Events) != 1 || commit.Events[0].EventType != "CallEnded" {
		t.Fatalf("outbox events = %#v, want one CallEnded", commit.Events)
	}
	var wire struct {
		Type    string `json:"type"`
		ActorID string `json:"actorId"`
		Payload struct {
			EndReason string `json:"endReason"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(commit.Events[0].Payload, &wire); err != nil {
		t.Fatalf("decode timeout outbox payload: %v", err)
	}
	if wire.Type != "call.ended" || wire.Payload.EndReason != model.EndReasonNoAnswer {
		t.Fatalf("timeout wire = %s/%s, want call.ended/no_answer", wire.Type, wire.Payload.EndReason)
	}
	if wire.ActorID != "system:rtc-ring-timeout-sweeper" {
		t.Fatalf("system actor = %q", wire.ActorID)
	}

	secondStore := newSweeperCallStore(ringingSession(
		now.Add(-30*time.Second),
		model.MaxParticipants1v1,
	))
	second := newSweeperOrchestrator(secondStore, now)
	if _, err := second.SweepRingTimeouts(context.Background()); err != nil {
		t.Fatalf("second deterministic sweep: %v", err)
	}
	secondStore.mu.Lock()
	secondKey := secondStore.commits[0].IdempotencyKey
	secondStore.mu.Unlock()
	if secondKey != commit.IdempotencyKey {
		t.Fatalf("system idempotency key is not deterministic: %q != %q", secondKey, commit.IdempotencyKey)
	}
}

func TestRingTimeoutSweeperFacetStopsWhenContextIsCancelled(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 20, 13, 5, 0, 0, time.UTC)
	store := newSweeperCallStore(nil)
	orchestrator := newSweeperOrchestrator(store, now)
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() {
		done <- orchestrator.RunRingTimeoutSweeper(ctx, time.Hour)
	}()

	select {
	case <-store.queryCalled:
	case <-time.After(time.Second):
		t.Fatal("sweeper did not run its initial scan")
	}
	cancel()

	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("RunRingTimeoutSweeper() error = %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("sweeper goroutine did not stop after cancellation")
	}
}

func TestRingTimeoutSweeperFacetRechecksAggregateAfterCASConflict(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.July, 20, 13, 10, 0, 0, time.UTC)
	store := newSweeperCallStore(ringingSession(
		now.Add(-30*time.Second),
		model.MaxParticipants1v1,
	))
	store.conflictOnce = true
	orchestrator := newSweeperOrchestrator(store, now)

	swept, err := orchestrator.SweepRingTimeouts(context.Background())
	if err != nil {
		t.Fatalf("SweepRingTimeouts() error = %v", err)
	}
	if swept != 0 {
		t.Fatalf("concurrently answered call swept = %d, want 0", swept)
	}

	store.mu.Lock()
	defer store.mu.Unlock()
	if store.findByIDCalls != 2 {
		t.Fatalf("authoritative reloads = %d, want 2", store.findByIDCalls)
	}
	if store.session.Status != model.StatusConnecting {
		t.Fatalf("session status = %s, want connecting", store.session.Status)
	}
	if len(store.noopReceipts) != 1 ||
		store.noopReceipts[0].CommandName != "RingTimeout" {
		t.Fatalf("no-op receipts = %#v", store.noopReceipts)
	}
}

func newSweeperOrchestrator(store application.CallStore, now time.Time) *application.CallOrchestrator {
	return application.NewCallOrchestrator(
		store,
		noopCallStateCache{},
		callsession.NewCallSessionService(),
		nil,
		nil,
		application.AllowRelationshipGateForTest(),
		"",
		application.WithClock(func() time.Time { return now }),
	)
}

type sweeperCallStore struct {
	mu sync.Mutex

	session          *model.CallSession
	oneToOneCutoff   time.Time
	groupCutoff      time.Time
	findByIDCalls    int
	findReceiptCalls int
	commits          []application.CallCommit
	noopReceipts     []application.CallNoopReceipt
	conflictOnce     bool
	queryCalled      chan struct{}
	queryOnce        sync.Once
}

func newSweeperCallStore(session *model.CallSession) *sweeperCallStore {
	return &sweeperCallStore{
		session:     cloneCallSession(session),
		queryCalled: make(chan struct{}),
	}
}

func (s *sweeperCallStore) CreateCall(context.Context, *model.CallSession) error {
	panic("CreateCall must not be used by the ring-timeout sweeper")
}

func (s *sweeperCallStore) FindCallByID(_ context.Context, id string) (*model.CallSession, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.findByIDCalls++
	if s.session == nil || s.session.ID != id {
		return nil, nil
	}
	return cloneCallSession(s.session), nil
}

func (s *sweeperCallStore) FindActiveCallForUser(context.Context, string) (*model.CallSession, error) {
	panic("FindActiveCallForUser must not be used by the ring-timeout sweeper")
}

func (s *sweeperCallStore) FindOverdueRingingCalls(
	_ context.Context,
	oneToOneCutoff time.Time,
	groupCutoff time.Time,
	_ int,
) ([]*model.CallSession, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.oneToOneCutoff = oneToOneCutoff
	s.groupCutoff = groupCutoff
	s.queryOnce.Do(func() { close(s.queryCalled) })
	if s.session == nil || s.session.Status != model.StatusRinging {
		return nil, nil
	}
	cutoff := oneToOneCutoff
	if s.session.MaxParticipants > model.MaxParticipants1v1 {
		cutoff = groupCutoff
	}
	if s.session.CreatedAt.After(cutoff) {
		return nil, nil
	}
	return []*model.CallSession{cloneCallSession(s.session)}, nil
}

func (s *sweeperCallStore) Commit(
	_ context.Context,
	commit application.CallCommit,
) (application.CallCommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.commits = append(s.commits, commit)
	if s.conflictOnce {
		s.conflictOnce = false
		concurrentlyAnswered := cloneCallSession(s.session)
		concurrentlyAnswered.Version++
		concurrentlyAnswered.Status = model.StatusConnecting
		concurrentlyAnswered.Participants[1].Status = model.ParticipantConnecting
		s.session = concurrentlyAnswered
		return application.CallCommitResult{}, application.ErrVersionConflict
	}
	stored := cloneCallSession(commit.Session)
	stored.Version = commit.ExpectedVersion + 1
	s.session = stored
	return application.CallCommitResult{Session: cloneCallSession(stored)}, nil
}

func (s *sweeperCallStore) FindReceipt(
	context.Context,
	string,
	string,
	string,
) (application.CallCommitResult, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.findReceiptCalls++
	return application.CallCommitResult{}, false, nil
}

func (s *sweeperCallStore) RecordNoopReceipt(
	_ context.Context,
	receipt application.CallNoopReceipt,
) (application.CallCommitResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.noopReceipts = append(s.noopReceipts, receipt)
	return application.CallCommitResult{
		Session: cloneCallSession(receipt.Session),
	}, nil
}

func (s *sweeperCallStore) ListCallsByUserID(
	context.Context,
	string,
	application.CallHistoryQuery,
) (application.CallHistoryPage, error) {
	panic("ListCallsByUserID must not be used by the ring-timeout sweeper")
}

type noopCallStateCache struct{}

func (noopCallStateCache) SetCallState(context.Context, *model.CallSession) error {
	return nil
}

func (noopCallStateCache) GetCallState(context.Context, string) (*model.CallSession, error) {
	return nil, nil
}

func cloneCallSession(session *model.CallSession) *model.CallSession {
	if session == nil {
		return nil
	}
	clone := *session
	clone.Participants = append([]model.Participant(nil), session.Participants...)
	return &clone
}
