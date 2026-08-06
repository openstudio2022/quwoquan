package http_test

import (
	"testing"

	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
)

func TestScopeCHostOutcomeActionsExcludeLifecycleOwnership(t *testing.T) {
	handler := &gatheringhttp.HostOutcomeHandler{}

	for _, action := range []string{
		"assign-co-host",
		"revoke-co-host",
		"transfer-organizer",
		"acknowledge-revision",
		"declare-arrival",
		"leave-early",
		"complete-self",
	} {
		resolved, owned := handler.ResolveAction(action)
		if !owned || resolved == nil {
			t.Fatalf("Scope C action %q was not resolved", action)
		}
	}

	for _, lifecycleAction := range []string{
		"complete",
		"end-early",
		"safety-terminate",
	} {
		resolved, owned := handler.ResolveAction(lifecycleAction)
		if owned || resolved != nil {
			t.Fatalf(
				"lifecycle action %q must be owned only by LifecycleHandler",
				lifecycleAction,
			)
		}
	}
}
