package assistant_run

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

type actionIntentMemoryJTIStore struct {
	mu       sync.Mutex
	consumed map[string]time.Time
}

func (s *actionIntentMemoryJTIStore) ConsumeActionIntent(
	_ context.Context,
	jti string,
	expiresAt time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.consumed[jti]; exists {
		return false, nil
	}
	s.consumed[jti] = expiresAt
	return true, nil
}

func TestActionIntentConsumerFailsClosedBeforeExecution(t *testing.T) {
	now := time.Now().UTC()
	store := &actionIntentMemoryJTIStore{
		consumed: map[string]time.Time{},
	}
	consumer, err := presentation.NewActionIntentConsumer(store)
	if err != nil {
		t.Fatalf("new action intent consumer: %v", err)
	}
	valid := validApproveActionIntent(now)
	expected := presentation.ActionIntentExpectation{
		IntentID:         valid.IntentID,
		Kind:             presentation.ActionIntentApproveTool,
		RequestDigest:    valid.RequestDigest,
		RunID:            valid.ApproveTool.RunID,
		ToolInvocationID: valid.ApproveTool.ToolInvocationID,
	}
	cases := []struct {
		name   string
		mutate func(*presentation.ActionIntent, *presentation.ActionIntentExpectation)
		want   error
	}{
		{
			name: "unknown kind",
			mutate: func(intent *presentation.ActionIntent, _ *presentation.ActionIntentExpectation) {
				intent.Kind = presentation.ActionIntentKind("Unknown")
			},
			want: presentation.ErrActionRejected,
		},
		{
			name: "expired",
			mutate: func(intent *presentation.ActionIntent, _ *presentation.ActionIntentExpectation) {
				intent.ExpiresAt = now
			},
			want: presentation.ErrActionIntentExpired,
		},
		{
			name: "digest mismatch",
			mutate: func(_ *presentation.ActionIntent, expectation *presentation.ActionIntentExpectation) {
				expectation.RequestDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
			},
			want: presentation.ErrActionIntentDigestMismatch,
		},
		{
			name: "target mismatch",
			mutate: func(_ *presentation.ActionIntent, expectation *presentation.ActionIntentExpectation) {
				expectation.ToolInvocationID = "tool_other"
			},
			want: presentation.ErrActionIntentTargetMismatch,
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			intent := valid
			approveTool := *valid.ApproveTool
			intent.ApproveTool = &approveTool
			expectation := expected
			testCase.mutate(&intent, &expectation)
			executions := 0
			if err := consumer.Consume(t.Context(), intent, expectation); err == nil {
				executions++
			} else if !errors.Is(err, testCase.want) {
				t.Fatalf("consume error = %v, want %v", err, testCase.want)
			}
			if executions != 0 {
				t.Fatalf("rejected action executed %d times", executions)
			}
		})
	}

	executions := 0
	execute := func() error {
		if err := consumer.Consume(t.Context(), valid, expected); err != nil {
			return err
		}
		executions++
		return nil
	}
	if err := execute(); err != nil {
		t.Fatalf("first action execution: %v", err)
	}
	if err := execute(); !errors.Is(err, presentation.ErrActionIntentReplay) {
		t.Fatalf("replay error = %v, want %v", err, presentation.ErrActionIntentReplay)
	}
	if executions != 1 {
		t.Fatalf("action executions = %d, want exactly one", executions)
	}
}

func TestActionIntentConsumerRequiresPersistentPort(t *testing.T) {
	if _, err := presentation.NewActionIntentConsumer(nil); err == nil {
		t.Fatal("expected missing action intent JTI store to fail fast")
	}
}

func validApproveActionIntent(now time.Time) presentation.ActionIntent {
	return presentation.ActionIntent{
		IntentID:      "intent_approval",
		Kind:          presentation.ActionIntentApproveTool,
		RequestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		JTI:           "jti_approval",
		IssuedAt:      now.Add(-time.Second),
		ExpiresAt:     now.Add(time.Minute),
		ApproveTool: &presentation.ApproveToolIntent{
			RunID:            "run_approval",
			ToolInvocationID: "tool_approval",
			Decision:         "approved",
			ApprovalPermit:   "permit_approval_0123456789",
			Capability:       "calendar.create_reminder",
			InputDigest:      "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
		},
	}
}
