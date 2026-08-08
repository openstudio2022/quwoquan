package local_contract

import (
	"encoding/json"
	"io/fs"
	"os"
	"path/filepath"
	"reflect"
	"sort"
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

// 关系能力位由服务端 NewRelationshipCapabilityView 独家裁定。端侧只能把 wire
// 结果搬进 RelationshipCapabilityViewData，不得自己算、不得改写、不得凭本地关注
// 标志位造一个能力对象——否则同一 viewer/target 会出现端云两套动作矩阵。
func TestAppConsumersDoNotRecalculateRelationshipCapability(t *testing.T) {
	t.Parallel()

	repoRoot := filepath.Clean(filepath.Join(userServiceRoot(t), "..", "..", ".."))
	appLib := filepath.Join(repoRoot, "quwoquan_app", "lib")
	canonicalPath := filepath.Join(
		appLib, "service", "user_service", "relationship", "persona_relationship",
		"application", "public", "relationship_capability_repository.dart",
	)

	canonicalAppValue := readContract(t, canonicalPath)
	for _, field := range []string{
		"required this.viewerPersonaId",
		"required this.targetPersonaId",
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
	if strings.Contains(canonicalAppValue, "copyWith") {
		t.Fatalf(
			"App canonical capability value exposes copyWith and can drift from the wire: %s",
			canonicalPath,
		)
	}

	builders := appFilesConstructing(t, appLib, "RelationshipCapabilityViewData(")
	if !reflect.DeepEqual(builders, []string{canonicalPath}) {
		t.Fatalf(
			"relationship capability may only be built from the wire in %s, built in %v",
			canonicalPath,
			builders,
		)
	}
}

// appFilesConstructing 返回 App production 树中构造该类型的全部文件。
func appFilesConstructing(t *testing.T, appLib string, constructor string) []string {
	t.Helper()
	var matches []string
	err := filepath.WalkDir(appLib, func(path string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() || filepath.Ext(path) != ".dart" {
			return nil
		}
		raw, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if strings.Contains(string(raw), constructor) {
			matches = append(matches, path)
		}
		return nil
	})
	if err != nil {
		t.Fatalf("scan App production tree: %v", err)
	}
	sort.Strings(matches)
	return matches
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
