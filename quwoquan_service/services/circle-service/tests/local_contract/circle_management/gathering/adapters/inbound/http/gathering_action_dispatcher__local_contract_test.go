package http_test

import (
	"testing"

	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// contract_ref: services/circle-service/contracts/circle_management/gathering/operations.yaml
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
func TestGatheringActionDispatcherOwnsAll28ActionOperationsOnce(t *testing.T) {
	lifecycle := []string{
		"publish", "cancel", "complete", "end-early", "safety-terminate",
	}
	participation := []string{
		"join-open", "apply", "withdraw-application", "review-application",
		"invite", "accept-invitation", "decline-invitation",
		"revoke-invitation", "leave", "remove", "reinstate",
		"pause-admission", "resume-admission", "change-capacity",
		"watch-availability", "unwatch-availability",
	}
	hostOutcome := []string{
		"assign-co-host", "revoke-co-host", "transfer-organizer",
		"acknowledge-revision", "declare-arrival", "leave-early",
		"complete-self",
	}
	seen := make(map[string]string)
	hostHandler := gatheringhttp.NewHostOutcomeHandler(&app.HostOutcomeFacade{})
	for _, action := range lifecycle {
		assertUniqueActionOwner(t, seen, action, "lifecycle")
		_, hostOwned := hostHandler.ResolveAction(action)
		if !gatheringhttp.IsLifecycleAction(action) ||
			gatheringhttp.IsParticipationAction(action) || hostOwned {
			t.Fatalf("action %q is not lifecycle-only", action)
		}
	}
	for _, action := range participation {
		assertUniqueActionOwner(t, seen, action, "participation")
		_, hostOwned := hostHandler.ResolveAction(action)
		if !gatheringhttp.IsParticipationAction(action) ||
			gatheringhttp.IsLifecycleAction(action) || hostOwned {
			t.Fatalf("action %q is not participation-only", action)
		}
	}
	for _, action := range hostOutcome {
		assertUniqueActionOwner(t, seen, action, "host-outcome")
		if _, ok := hostHandler.ResolveAction(action); !ok ||
			gatheringhttp.IsLifecycleAction(action) ||
			gatheringhttp.IsParticipationAction(action) {
			t.Fatalf("action %q is not host/outcome-only", action)
		}
	}
	if len(seen) != 28 {
		t.Fatalf("action dispatcher owns %d operations, want 28", len(seen))
	}
}

func assertUniqueActionOwner(
	t *testing.T,
	seen map[string]string,
	action string,
	owner string,
) {
	t.Helper()
	if previous, exists := seen[action]; exists {
		t.Fatalf("action %q is owned by %s and %s", action, previous, owner)
	}
	seen[action] = owner
}
