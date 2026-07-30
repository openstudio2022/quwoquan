package local_contract

import (
	"encoding/json"
	"path/filepath"
	"strings"
	"testing"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

func TestRelationshipCapabilityPolicyOwnsEverySurfaceActionMatrix(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		facts relmodel.RelationshipCapabilityFacts
		check func(*testing.T, relationshipapp.RelationshipCapabilityView)
	}{
		{
			name: "not following can follow and greet",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
			},
			check: func(t *testing.T, view relationshipapp.RelationshipCapabilityView) {
				if view.RelationState != "not_following" || !view.CanFollow || !view.CanGreet {
					t.Fatalf("unexpected not-following capability: %+v", view)
				}
			},
		},
		{
			name: "mutual enables the established relationship actions",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
				Relationship: relmodel.RelationshipState{IsMutual: true},
			},
			check: func(t *testing.T, view relationshipapp.RelationshipCapabilityView) {
				if view.RelationState != "mutual" || view.CanFollow || view.CanGreet ||
					!view.CanUnfollow || !view.CanOpenConversation ||
					!view.CanCreateDirectConversation || !view.CanSendMessage ||
					!view.CanStartVoiceCall || !view.CanStartVideoCall {
					t.Fatalf("unexpected mutual capability: %+v", view)
				}
			},
		},
		{
			name: "followed by exposes follow back",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
				Relationship: relmodel.RelationshipState{IsFollowedBy: true},
			},
			check: func(t *testing.T, view relationshipapp.RelationshipCapabilityView) {
				if view.RelationState != "followed_by" || !view.CanFollow || !view.CanFollowBack {
					t.Fatalf("unexpected followed-by capability: %+v", view)
				}
			},
		},
		{
			name: "formal conversation enables open and send but not another greeting",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
				HasFormalConversation: true,
			},
			check: func(t *testing.T, view relationshipapp.RelationshipCapabilityView) {
				if !view.CanOpenConversation || !view.CanSendMessage || view.CanGreet {
					t.Fatalf("unexpected formal-conversation capability: %+v", view)
				}
			},
		},
		{
			name: "pending greeting cannot be sent again",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
				HasPendingGreeting: true,
			},
			check: func(t *testing.T, view relationshipapp.RelationshipCapabilityView) {
				if view.CanGreet || !view.HasPendingGreeting {
					t.Fatalf("unexpected pending-greeting capability: %+v", view)
				}
			},
		},
		{
			name: "self fails every relationship action closed",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "same", TargetPersonaID: "same",
				HasFormalConversation: true,
			},
			check: assertRelationshipActionsDenied,
		},
		{
			name: "block overrides inconsistent mutual and conversation facts",
			facts: relmodel.RelationshipCapabilityFacts{
				ViewerPersonaID: "viewer", TargetPersonaID: "target",
				Relationship: relmodel.RelationshipState{IsMutual: true},
				IsBlocked:    true, HasFormalConversation: true,
			},
			check: assertRelationshipActionsDenied,
		},
	}

	for _, current := range tests {
		current := current
		t.Run(current.name, func(t *testing.T) {
			t.Parallel()
			view := relationshipapp.NewRelationshipCapabilityView(current.facts)
			current.check(t, view)
		})
	}
}

func TestRelationshipCapabilityViewHasExactlyTheCanonicalWireFields(t *testing.T) {
	t.Parallel()
	view := relationshipapp.NewRelationshipCapabilityView(
		relmodel.RelationshipCapabilityFacts{
			ViewerPersonaID: "viewer", TargetPersonaID: "target",
			Relationship: relmodel.RelationshipState{IsMutual: true},
		},
	)
	raw, err := json.Marshal(view)
	if err != nil {
		t.Fatalf("marshal capability view: %v", err)
	}
	var fields map[string]any
	if err := json.Unmarshal(raw, &fields); err != nil {
		t.Fatalf("decode capability view: %v", err)
	}
	want := []string{
		"viewerPersonaId", "targetPersonaId", "relationState",
		"canFollow", "canUnfollow", "canFollowBack", "canGreet",
		"canOpenConversation", "canCreateDirectConversation", "canSendMessage",
		"hasPendingGreeting", "hasFormalConversation", "canStartVoiceCall",
		"canStartVideoCall", "isBlocked", "isBlockedBy",
	}
	if len(fields) != len(want) {
		t.Fatalf("capability wire field count drift: got %d fields: %v", len(fields), fields)
	}
	for _, field := range want {
		if _, exists := fields[field]; !exists {
			t.Fatalf("capability wire missing %q: %v", field, fields)
		}
	}
	if _, exists := fields["isMutual"]; exists {
		t.Fatalf("derived isMutual must not escape the canonical wire: %v", fields)
	}
}

func TestInboundHandlersOnlyAssembleCapabilityFacts(t *testing.T) {
	t.Parallel()
	serviceRoot := userServiceRoot(t)
	paths := []string{
		filepath.Join(
			serviceRoot, "internal", "account", "user_account", "adapters", "inbound", "http",
			"user_handler_relationships.go",
		),
		filepath.Join(
			serviceRoot, "internal", "relationship", "contact_discovery_record", "adapters", "inbound", "http",
			"handler.go",
		),
	}
	for _, path := range paths {
		source := readContract(t, path)
		if strings.Contains(source, "buildRelationshipCapabilityView") {
			t.Fatalf("handler retains a capability policy implementation: %s", path)
		}
		if !strings.Contains(source, "NewRelationshipCapabilityView") {
			t.Fatalf("handler does not delegate to the canonical capability mapper: %s", path)
		}
	}
}

func TestAppConsumersDoNotRecalculateRelationshipCapability(t *testing.T) {
	t.Parallel()

	repoRoot := filepath.Clean(filepath.Join(userServiceRoot(t), "..", "..", ".."))
	files := map[string][]string{
		filepath.Join(
			repoRoot, "quwoquan_app", "lib", "cloud", "services", "user",
			"relationship_capability_repository.dart",
		): {
			"fromFollowFlags",
			"_defaultCanFollow",
			"RelationshipCapabilityDto copyWith",
		},
		filepath.Join(
			repoRoot, "quwoquan_app", "lib", "ui", "user", "providers",
			"profile_state_provider.dart",
		): {
			"capability.copyWith",
			"fromFollowFlags",
			"_copyCapabilityWithFollowState",
		},
		filepath.Join(
			repoRoot, "quwoquan_app", "lib", "ui", "user", "pages",
			"profile_stats_page.dart",
		): {"fromFollowFlags"},
		filepath.Join(
			repoRoot, "quwoquan_app", "lib", "cloud", "services", "user",
			"contact_discovery_repository.dart",
		): {"RelationshipCapabilityDto("},
		filepath.Join(
			repoRoot, "quwoquan_app", "packages", "quwoquan_cloud_contracts", "lib", "src", "user",
			"public_profile_query_contracts.dart",
		): {"SocialRelationshipCapabilityProjection"},
		filepath.Join(
			repoRoot, "quwoquan_app", "packages", "quwoquan_cloud_contracts", "lib", "src", "user",
			"user_homepage_query_contracts.dart",
		): {"HomepageRelationshipCapabilityProjection"},
	}
	for path, banned := range files {
		source := readContract(t, path)
		for _, token := range banned {
			if strings.Contains(source, token) {
				t.Fatalf("App consumer retains relationship capability policy %q: %s", token, path)
			}
		}
	}

	canonicalAppValue := readContract(t, filepath.Join(
		repoRoot, "quwoquan_app", "lib", "cloud", "services", "user",
		"relationship_capability_repository.dart",
	))
	for _, field := range []string{
		"required this.relationState",
		"required this.canFollow",
		"required this.canUnfollow",
		"required this.canFollowBack",
		"required this.canGreet",
		"required this.canOpenConversation",
		"required this.canCreateDirectConversation",
		"required this.canSendMessage",
		"required this.hasPendingGreeting",
		"required this.hasFormalConversation",
		"required this.canStartVoiceCall",
		"required this.canStartVideoCall",
		"required this.isBlocked",
		"required this.isBlockedBy",
	} {
		if !strings.Contains(canonicalAppValue, field) {
			t.Fatalf("App canonical capability value is not strict for %q", field)
		}
	}
}

func assertRelationshipActionsDenied(
	t *testing.T,
	view relationshipapp.RelationshipCapabilityView,
) {
	t.Helper()
	if view.CanFollow || view.CanUnfollow || view.CanFollowBack || view.CanGreet ||
		view.CanOpenConversation || view.CanCreateDirectConversation ||
		view.CanSendMessage || view.CanStartVoiceCall || view.CanStartVideoCall {
		t.Fatalf("relationship actions must fail closed: %+v", view)
	}
}
