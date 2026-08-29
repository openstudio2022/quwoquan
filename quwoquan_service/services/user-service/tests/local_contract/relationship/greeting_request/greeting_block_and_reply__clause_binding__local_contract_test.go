// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t3
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003.t3
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003.t4
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-003.t5
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// SIT-002.t3：任一方向拉黑时，关注/打招呼/建会话/发消息/1v1 RTC 能力位全部关闭。
func TestBlockedEitherWayClosesEveryGuardedSurface(t *testing.T) {
	t.Parallel()

	for _, facts := range []relmodel.RelationshipCapabilityFacts{
		{ViewerPersonaID: "viewer", TargetPersonaID: "target", IsBlocked: true},
		{ViewerPersonaID: "viewer", TargetPersonaID: "target", IsBlockedBy: true},
		{
			ViewerPersonaID: "viewer", TargetPersonaID: "target",
			IsBlocked: true, IsBlockedBy: true,
			Relationship: relmodel.RelationshipState{IsMutual: true},
		},
	} {
		cap := relmodel.DeriveRelationshipCapability(facts)
		for _, open := range []struct {
			name string
			ok   bool
		}{
			{"CanFollow", cap.CanFollow},
			{"CanFollowBack", cap.CanFollowBack},
			{"CanGreet", cap.CanGreet},
			{"CanCreateDirectConversation", cap.CanCreateDirectConversation},
			{"CanSendMessage", cap.CanSendMessage},
			{"CanStartVoiceCall", cap.CanStartVoiceCall},
			{"CanStartVideoCall", cap.CanStartVideoCall},
		} {
			if open.ok {
				t.Fatalf("blocked facts %+v still allows %s", facts, open.name)
			}
		}
	}
}

// SIT-003.t1：非 mutual 未拉黑可发 pending。
func TestNonMutualUnblockedCanGreet(t *testing.T) {
	t.Parallel()

	cap := relmodel.DeriveRelationshipCapability(relmodel.RelationshipCapabilityFacts{
		ViewerPersonaID: "viewer", TargetPersonaID: "target",
	})
	if !cap.CanGreet || cap.RelationState != "not_following" {
		t.Fatalf("non-mutual unblocked must allow greet, got %+v", cap)
	}
}

// SIT-003.t2：同一 requester-target 只能有一条 pending，重复返回结构化错误。
func TestDuplicatePendingGreetingHasStructuredError(t *testing.T) {
	t.Parallel()

	root := userSitRepoRoot(t)
	service := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/internal/relationship/greeting_request/application/greeting_service.go"))
	if !strings.Contains(service, "AppErrorFromGreetingDuplicatePending") {
		t.Fatal("duplicate pending must return structured GreetingDuplicatePending")
	}
	errorsYAML := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/contracts/relationship/greeting_request/errors.yaml"))
	if !strings.Contains(errorsYAML, "code: USER.GREETING.duplicate_pending") {
		t.Fatal("greeting_request errors.yaml must declare USER.GREETING.duplicate_pending")
	}
}

// SIT-003.t3 / t4：回复后创建或复用 1v1，并写入 promotedConversationId。
func TestGreetingReplyCreatesOrReusesConversationWithPromotedId(t *testing.T) {
	t.Parallel()

	root := userSitRepoRoot(t)
	ops := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml"))
	if !strings.Contains(ops, "promotedConversationId") {
		t.Fatal("reply operation must write promotedConversationId")
	}
	events := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/contracts/relationship/greeting_request/events.yaml"))
	if !strings.Contains(events, "GreetingRequestReplied") {
		t.Fatal("GreetingRequestReplied event missing")
	}
	if !strings.Contains(events, "promotedConversationId") {
		t.Fatal("GreetingRequestReplied payload must include promotedConversationId")
	}
	service := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/internal/relationship/greeting_request/application/greeting_service.go"))
	if !strings.Contains(service, `"promotedConversationId"`) {
		t.Fatal("reply path must persist promotedConversationId before emitting the event")
	}
}

// SIT-003.t5：回复建会话不自动 FollowEdge、不改 RelationshipState。
func TestGreetingReplyDoesNotCreateFollowEdge(t *testing.T) {
	t.Parallel()

	root := userSitRepoRoot(t)
	service := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/internal/relationship/greeting_request/application/greeting_service.go"))
	for _, forbidden := range []string{
		"CommandFollow",
		"PersonaFollowStateChanged",
	} {
		if strings.Contains(service, forbidden) {
			t.Errorf("greeting reply must not touch follow edges via %q", forbidden)
		}
	}
}

// SIT-003.t1 后半：pending 请求不进入普通会话列表。
func TestGreetingPendingKeptOutOfChatInboxProjection(t *testing.T) {
	t.Parallel()

	root := userSitRepoRoot(t)
	ops := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/user-service/contracts/relationship/greeting_request/operations.yaml"))
	for _, needle := range []string{"inbox", "outbox"} {
		if !strings.Contains(ops, needle) {
			t.Errorf("greeting operations missing %q surface", needle)
		}
	}
	inbox := mustReadUser(t, filepath.Join(root,
		"quwoquan_service/services/chat-service/contracts/chat/chat_inbox_view/object.yaml"))
	if strings.Contains(inbox, "GreetingRequest") {
		t.Fatal("chat inbox must not project pending GreetingRequest as a conversation row")
	}
}

func mustReadUser(t *testing.T, path string) string {
	t.Helper()
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(body)
}

func userSitRepoRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "specs", "feature-tree")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repository root not found")
		}
		dir = parent
	}
}
