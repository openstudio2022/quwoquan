// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
)

type countingFrozenPolicyResolver struct {
	calls int
	err   error
}

func (resolver *countingFrozenPolicyResolver) ResolveFrozenPolicy(
	_ context.Context,
	policyID string,
	_ string,
	skillID string,
	domainID string,
) (runruntime.FrozenPolicySelection, error) {
	resolver.calls++
	if resolver.err != nil {
		return runruntime.FrozenPolicySelection{}, resolver.err
	}
	return testRunPolicyResolver().ResolveFrozenPolicy(
		context.Background(),
		policyID,
		"persona-1",
		skillID,
		domainID,
	)
}

func TestStartRunFreezesPolicyBeforeInsertAndReplayNeverRebuckets(t *testing.T) {
	runtime := assistantruntest.NewMemoryRuntime()
	resolver := &countingFrozenPolicyResolver{}
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionAuthorizerFunc(func(context.Context, string, string) error { return nil }),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		resolver,
	)
	command := runruntime.StartCommand{
		UserID:            "account-1",
		PersonaID:         "persona-1",
		SessionID:         "session-1",
		ClientRequestID:   "run-1",
		IntentKind:        "answer",
		InputText:         "测试冻结策略",
		RequestedSkillID:  "general_qa",
		RequestedDomainID: "assistant",
	}
	first, err := commands.Start(t.Context(), command)
	if err != nil {
		t.Fatal(err)
	}
	replay, err := commands.Start(t.Context(), command)
	if err != nil {
		t.Fatal(err)
	}
	if resolver.calls != 1 || first.RunID != replay.RunID ||
		first.FrozenPolicySelection.ReleaseDigest != testPolicyReleaseDigest ||
		replay.FrozenPolicySelection.ReleaseDigest != first.FrozenPolicySelection.ReleaseDigest ||
		replay.FrozenPolicySelection.RolloutRevision != first.FrozenPolicySelection.RolloutRevision {
		t.Fatalf("calls=%d first=%+v replay=%+v", resolver.calls, first, replay)
	}

}

func TestPolicyResolverFailureDoesNotWriteRun(t *testing.T) {
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionAuthorizerFunc(func(context.Context, string, string) error { return nil }),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		&countingFrozenPolicyResolver{err: errors.New("rollout storage unavailable")},
	)
	_, err := commands.Start(t.Context(), runruntime.StartCommand{
		UserID:          "account-2",
		PersonaID:       "persona-2",
		SessionID:       "session-2",
		ClientRequestID: "run-failed-policy",
		IntentKind:      "answer",
		InputText:       "must fail",
	})
	if !errors.Is(err, runruntime.ErrPolicyUnavailable) {
		t.Fatalf("policy resolver failure=%v", err)
	}
	if _, readErr := runtime.LoadByRequest(
		t.Context(),
		"account-2",
		"session-2",
		"run-failed-policy",
	); !errors.Is(readErr, runruntime.ErrRunNotFound) {
		t.Fatalf("failed policy selection persisted run: %v", readErr)
	}
}
