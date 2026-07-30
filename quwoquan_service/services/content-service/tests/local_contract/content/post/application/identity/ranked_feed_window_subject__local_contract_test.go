// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package identity_test

import (
	"strings"
	"testing"

	identity "quwoquan_service/services/content-service/internal/content/post/application/identity"
)

func TestRankedFeedWindowSubjectKeepsNamedActorQuotaAcrossSessions(t *testing.T) {
	first := identity.RankedFeedWindowSubjectID("actor-1", "session-a")
	second := identity.RankedFeedWindowSubjectID(" actor-1 ", "session-b")
	if first == "" || first != second {
		t.Fatalf("named actor subjects = (%q, %q), want one stable non-empty subject", first, second)
	}
}

func TestRankedFeedWindowSubjectIsolatesIdentitylessPublicSessions(t *testing.T) {
	first := identity.RankedFeedWindowSubjectID("", "session-a")
	second := identity.RankedFeedWindowSubjectID(
		identity.AnonymousFallbackPersonaID,
		"session-b",
	)
	if first == "" || second == "" || first == second {
		t.Fatalf("anonymous subjects = (%q, %q), want distinct non-empty session subjects", first, second)
	}
	if strings.Contains(first, identity.AnonymousFallbackPersonaID) ||
		strings.Contains(second, identity.AnonymousFallbackPersonaID) {
		t.Fatalf("anonymous fallback actor leaked into quota subject: (%q, %q)", first, second)
	}
	if got := identity.RankedFeedWindowSubjectID("", "   "); got != "" {
		t.Fatalf("identity-less request without a session subject = %q, want fail-closed empty", got)
	}
}

func TestRankedFeedWindowSubjectNamespacesActorAndAnonymousSession(t *testing.T) {
	actor := identity.RankedFeedWindowSubjectID("session-a", "ignored")
	anonymous := identity.RankedFeedWindowSubjectID("", "session-a")
	if actor == anonymous {
		t.Fatalf("actor and anonymous-session namespaces collided: %q", actor)
	}
}
