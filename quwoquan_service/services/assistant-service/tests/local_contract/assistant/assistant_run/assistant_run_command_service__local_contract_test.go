package assistant_run_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestAssistantRunCommandServiceOwnsIdempotencyAndJournal(t *testing.T) {
	t.Parallel()

	repository := newMemoryRunRepository()
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	skillPackages := &rotatingSkillPackageResolver{
		packageID:     "assistant.session.skills",
		releaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
	service := runruntime.NewCommandService(
		repository,
		runruntime.SessionAuthorizerFunc(func(
			_ context.Context,
			userID string,
			sessionID string,
		) error {
			if userID != "user-1" || sessionID != "session-1" {
				return errors.New("session not found")
			}
			return nil
		}),
		skillPackages,
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time { return now },
		nil,
		testPolicyResolver(),
	)
	command := runruntime.StartCommand{
		UserID:          "user-1",
		SessionID:       "session-1",
		ClientRequestID: "request-1",
		InputText:       "核对公开资料后给出引用答案",
	}

	first, err := service.Start(context.Background(), command)
	if err != nil {
		t.Fatalf("start first run: %v", err)
	}
	skillPackages.releaseDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	replayed, err := service.Start(context.Background(), command)
	if err != nil {
		t.Fatalf("replay start run: %v", err)
	}
	if replayed.RunID != first.RunID {
		t.Fatalf("idempotency replay created another run: %s != %s", replayed.RunID, first.RunID)
	}
	if first.SkillPackageID != "assistant.session.skills" ||
		first.SkillPackageReleaseDigest !=
			"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ||
		replayed.SkillPackageReleaseDigest != first.SkillPackageReleaseDigest ||
		skillPackages.calls != 1 {
		t.Fatalf(
			"Skill package was not frozen: first=%+v replay=%+v activeReads=%d",
			first,
			replayed,
			skillPackages.calls,
		)
	}
	conflicting := command
	conflicting.InputText = "不同用户意图"
	if _, err := service.Start(context.Background(), conflicting); !errors.Is(
		err,
		runruntime.ErrRevisionConflict,
	) {
		t.Fatalf("same key with different input must conflict, got %v", err)
	}
	if _, err := service.Get(context.Background(), "user-2", first.RunID); !errors.Is(
		err,
		runruntime.ErrRunNotFound,
	) {
		t.Fatalf("cross-owner read must look not found, got %v", err)
	}
	events, err := service.EventsAfter(
		context.Background(),
		"user-1",
		first.RunID,
		0,
		10,
	)
	if err != nil {
		t.Fatalf("read journal: %v", err)
	}
	if len(events) != 1 ||
		events[0].Sequence != 1 ||
		events[0].Kind != "run_accepted" {
		t.Fatalf("unexpected initial journal: %#v", events)
	}
}

func TestAssistantRunCommandServiceClosesCommandsWithCAS(t *testing.T) {
	t.Parallel()

	repository := newMemoryRunRepository()
	now := time.Date(2026, 7, 31, 12, 0, 0, 0, time.UTC)
	service := runruntime.NewCommandService(
		repository,
		runruntime.SessionAuthorizerFunc(func(
			context.Context,
			string,
			string,
		) error {
			return nil
		}),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		func() time.Time {
			now = now.Add(time.Second)
			return now
		},
		nil,
		testPolicyResolver(),
	)
	run, err := service.Start(context.Background(), runruntime.StartCommand{
		UserID:          "user-1",
		SessionID:       "session-1",
		ClientRequestID: "request-commands",
		InputText:       "执行一个可暂停任务",
	})
	if err != nil {
		t.Fatalf("start run: %v", err)
	}
	run, err = service.Pause(
		context.Background(),
		"user-1",
		run.RunID,
		"command-pause",
		"用户暂离",
	)
	if err != nil || run.State.WireName() != "paused" {
		t.Fatalf("pause run: state=%s err=%v", run.State, err)
	}
	run, err = service.Resume(
		context.Background(),
		"user-1",
		run.RunID,
		"command-resume",
	)
	if err != nil || run.State.WireName() != "orienting" {
		t.Fatalf("resume run: state=%s err=%v", run.State, err)
	}
	run, err = service.Steer(
		context.Background(),
		"user-1",
		run.RunID,
		"command-steer",
		"只采用可回查来源",
	)
	if err != nil || run.GoalRevision != 1 {
		t.Fatalf("steer run: goalRevision=%d err=%v", run.GoalRevision, err)
	}
	run, err = service.Cancel(
		context.Background(),
		"user-1",
		run.RunID,
		"command-cancel",
	)
	if err != nil || run.State.WireName() != "cancelled" || run.CompletedAt == nil {
		t.Fatalf("cancel run: state=%s completedAt=%v err=%v", run.State, run.CompletedAt, err)
	}
	revision := run.Revision
	run, err = service.Cancel(
		context.Background(),
		"user-1",
		run.RunID,
		"command-cancel",
	)
	if err != nil || run.Revision != revision {
		t.Fatalf("terminal cancel must be idempotent: revision=%d err=%v", run.Revision, err)
	}
	events, err := service.EventsAfter(
		context.Background(),
		"user-1",
		run.RunID,
		1,
		10,
	)
	if err != nil {
		t.Fatalf("read command journal: %v", err)
	}
	if len(events) != 4 {
		t.Fatalf("expected pause/resume/steer/cancel events, got %#v", events)
	}
	for index, event := range events {
		want := int64(index + 2)
		if event.Sequence != want {
			t.Fatalf("journal sequence gap at %d: got %d want %d", index, event.Sequence, want)
		}
	}
}

type memoryRunRepository struct {
	mu       sync.Mutex
	runs     map[string]runruntime.Run
	requests map[string]string
	events   map[string][]runruntime.JournalEvent
	receipts map[string]runruntime.CommandReceipt
}

func newMemoryRunRepository() *memoryRunRepository {
	return &memoryRunRepository{
		runs:     make(map[string]runruntime.Run),
		requests: make(map[string]string),
		events:   make(map[string][]runruntime.JournalEvent),
		receipts: make(map[string]runruntime.CommandReceipt),
	}
}

func (r *memoryRunRepository) Load(
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

func (r *memoryRunRepository) LoadByRequest(
	_ context.Context,
	userID string,
	sessionID string,
	clientRequestID string,
) (runruntime.Run, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	runID, ok := r.requests[userID+"\x00"+sessionID+"\x00"+clientRequestID]
	if !ok {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return r.runs[runID], nil
}

func (r *memoryRunRepository) Commit(
	_ context.Context,
	expectedRevision int64,
	run runruntime.Run,
	events []runruntime.JournalEvent,
	receipt *runruntime.CommandReceipt,
) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	current, found := r.runs[run.RunID]
	if found {
		if current.Revision != expectedRevision {
			return runruntime.ErrRevisionConflict
		}
	} else if expectedRevision != 0 {
		return runruntime.ErrRevisionConflict
	}
	requestKey := run.UserID + "\x00" + run.SessionID + "\x00" + run.ClientRequestID
	if existingID, ok := r.requests[requestKey]; ok && existingID != run.RunID {
		return runruntime.ErrRevisionConflict
	}
	journal := r.events[run.RunID]
	lastSequence := int64(0)
	if len(journal) > 0 {
		lastSequence = journal[len(journal)-1].Sequence
	}
	for _, event := range events {
		if event.Sequence != lastSequence+1 {
			return runruntime.ErrRevisionConflict
		}
		lastSequence = event.Sequence
		journal = append(journal, event)
	}
	r.runs[run.RunID] = run
	r.requests[requestKey] = run.RunID
	r.events[run.RunID] = journal
	if receipt != nil {
		key := receipt.RunID + "\x00" + receipt.CommandID
		if _, exists := r.receipts[key]; exists {
			return runruntime.ErrRevisionConflict
		}
		r.receipts[key] = *receipt
	}
	return nil
}

func (r *memoryRunRepository) LoadCommandReceipt(
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

func (r *memoryRunRepository) EventsAfter(
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

func (r *memoryRunRepository) LatestSequence(
	_ context.Context,
	runID string,
) (int64, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	run, ok := r.runs[runID]
	if !ok {
		return 0, runruntime.ErrRunNotFound
	}
	return run.JournalSequence, nil
}
