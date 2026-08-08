// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func TestAssistantRunAppliesExplicitSkillSettingAgainstFrozenPackage(t *testing.T) {
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
		runruntime.SessionResolverFunc(func(context.Context, string, string) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		packages,
		runruntime.StartAccessPolicyFunc(func(
			ctx context.Context,
			request runruntime.StartAccessRequest,
		) error {
			policyCalls++
			identity, frozen := skillpkg.PackageReleaseFromContext(ctx)
			if !frozen || identity.PackageID != packages.packageID ||
				identity.ReleaseDigest != packages.releaseDigest {
				t.Fatalf("setting gate did not receive frozen package: %+v frozen=%v", identity, frozen)
			}
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
		runruntime.WithPolicyResolver(testPolicyResolver()),
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
	if packages.calls != 1 || packages.membershipCalls != 1 {
		t.Fatalf(
			"disabled Skill package reads=%d membership=%d, want 1/1",
			packages.calls,
			packages.membershipCalls,
		)
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
	if policyCalls != 2 || packages.calls != 2 || packages.membershipCalls != 2 {
		t.Fatalf(
			"policy/package/membership calls=%d/%d/%d, want 2/2/2",
			policyCalls,
			packages.calls,
			packages.membershipCalls,
		)
	}
	for _, identity := range packages.membershipRelease {
		if identity.PackageID != packages.packageID ||
			identity.ReleaseDigest != packages.releaseDigest {
			t.Fatalf("membership escaped frozen package: %+v", identity)
		}
	}
}
