package recommendation

import (
	"context"
	"errors"
	"testing"
	"time"
)

type subjectClosureGuardStub struct {
	closed bool
	err    error
}

func (stub subjectClosureGuardStub) IsSubjectClosed(
	context.Context,
	string,
) (bool, error) {
	return stub.closed, stub.err
}

func TestHotPathClosedSubjectCannotRematerializeState(t *testing.T) {
	redis := newMockRedis()
	hotPath := NewHotPath(
		redis,
		WithSubjectClosureGuard(subjectClosureGuardStub{closed: true}),
	)
	ctx := context.Background()

	if err := hotPath.ProcessSignal(ctx, BehaviorSignal{
		UserID:        "closed-user",
		SessionID:     "session-1",
		ClientEventID: "event-1",
		ContentID:     "post-1",
		Action:        "like",
		Tags:          []string{"travel"},
	}); err != nil {
		t.Fatalf("closed-subject signal should be acknowledged: %v", err)
	}
	accepted, err := hotPath.AcceptEvent(ctx, BehaviorSignal{
		UserID:        "closed-user",
		ClientEventID: "event-1",
	})
	if err != nil {
		t.Fatalf("closed-subject dedup should not fail: %v", err)
	}
	if accepted {
		t.Fatal("closed-subject event must not be accepted")
	}
	if err := hotPath.RecordServed(
		ctx,
		"closed-user",
		[]FeedItem{{ContentID: "post-1"}},
		time.Now().UTC(),
	); err != nil {
		t.Fatalf("closed-subject exposure should be acknowledged: %v", err)
	}
	filtered, err := hotPath.FilterCandidates(
		ctx,
		"closed-user",
		[]ContentCandidate{{ContentID: "post-1"}},
		time.Now().UTC(),
	)
	if err != nil {
		t.Fatalf("closed-subject filtering failed: %v", err)
	}
	if len(filtered) != 0 {
		t.Fatalf("closed subject received %d candidates", len(filtered))
	}
	state, err := hotPath.GetSessionState(ctx, "closed-user", "session-1")
	if err != nil {
		t.Fatalf("closed-subject session read failed: %v", err)
	}
	if len(state.TagWeights) != 0 ||
		len(state.HiddenAuthorIDs) != 0 ||
		len(state.HiddenContentTypes) != 0 {
		t.Fatalf("closed-subject state must be empty: %#v", state)
	}
	if len(redis.data) != 0 || len(redis.sets) != 0 || len(redis.hashes) != 0 {
		t.Fatalf(
			"closed-subject request rematerialized Redis state: data=%v sets=%v hashes=%v",
			redis.data,
			redis.sets,
			redis.hashes,
		)
	}
}

func TestHotPathSubjectGuardFailureFailsClosed(t *testing.T) {
	redis := newMockRedis()
	guardErr := errors.New("guard unavailable")
	hotPath := NewHotPath(
		redis,
		WithSubjectClosureGuard(subjectClosureGuardStub{err: guardErr}),
	)

	err := hotPath.ProcessSignal(context.Background(), BehaviorSignal{
		UserID:    "user-1",
		SessionID: "session-1",
		ContentID: "post-1",
		Action:    "like",
		Tags:      []string{"travel"},
	})
	if !errors.Is(err, guardErr) {
		t.Fatalf("expected guard failure, got %v", err)
	}
	if len(redis.data) != 0 || len(redis.sets) != 0 || len(redis.hashes) != 0 {
		t.Fatal("guard failure must not write recommendation state")
	}
}
