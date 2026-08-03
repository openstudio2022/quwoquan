// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

func TestAssistantRunAppliesExplicitSkillSettingBeforeFreezingPackage(t *testing.T) {
	t.Parallel()
	repository := newMemoryRunRepository()
	packages := &rotatingSkillPackageResolver{
		packageID:     "assistant.session.skills",
		releaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	}
	disabled := true
	policyCalls := 0
	service := runruntime.NewCommandService(
		repository,
		runruntime.SessionAuthorizerFunc(func(context.Context, string, string) error { return nil }),
		packages,
		runruntime.StartAccessPolicyFunc(func(
			_ context.Context,
			request runruntime.StartAccessRequest,
		) error {
			policyCalls++
			if request.AccountID != "user-1" || request.SkillID != "travel_companion" {
				t.Fatalf("policy identity=%s/%s", request.AccountID, request.SkillID)
			}
			if disabled {
				return runruntime.ErrSkillDisabled
			}
			return nil
		}),
		func() time.Time { return time.Date(2026, 8, 2, 13, 0, 0, 0, time.UTC) },
		nil,
		testPolicyResolver(),
	)
	command := runruntime.StartCommand{
		UserID:           "user-1",
		SessionID:        "session-1",
		ClientRequestID:  "setting-gate-1",
		InputText:        "用旅行管家安排杭州周末游",
		RequestedSkillID: "travel_companion",
	}
	if _, err := service.Start(context.Background(), command); !errors.Is(err, runruntime.ErrSkillDisabled) {
		t.Fatalf("disabled Skill start error=%v", err)
	}
	if packages.calls != 0 {
		t.Fatalf("disabled Skill resolved package %d time(s)", packages.calls)
	}
	disabled = false
	run, err := service.Start(context.Background(), command)
	if err != nil || run.RequestedSkillID != "travel_companion" {
		t.Fatalf("enabled Skill run=%+v error=%v", run, err)
	}
	disabled = true
	replayed, err := service.Start(context.Background(), command)
	if err != nil || replayed.RunID != run.RunID {
		t.Fatalf("idempotent replay run=%+v error=%v", replayed, err)
	}
	if policyCalls != 2 || packages.calls != 1 {
		t.Fatalf("policy/package calls=%d/%d, want 2/1", policyCalls, packages.calls)
	}
}
