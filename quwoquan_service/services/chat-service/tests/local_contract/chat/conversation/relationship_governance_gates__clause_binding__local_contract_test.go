// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t3
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t5
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t3
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t4
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t5
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t6
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-004.t7
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// SIT-002.t3 服务端拒绝面：chat / rtc 契约必须有 blocked / not_mutual 结构化错误。
func TestBlockedSurfacesHaveServerRejectionCodes(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	for _, pathCode := range []struct {
		rel  string
		code string
	}{
		{"quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml", "CHAT.USER.blocked"},
		{"quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml", "CHAT.USER.not_mutual"},
		{"quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml", "CHAT.USER.greeting_required"},
		{"quwoquan_service/services/rtc-service/contracts/rtc/call_session/errors.yaml", "RTC.USER.blocked"},
		{"quwoquan_service/services/rtc-service/contracts/rtc/call_session/errors.yaml", "RTC.USER.not_mutual"},
	} {
		body := mustReadChat(t, filepath.Join(root, pathCode.rel))
		if !strings.Contains(body, "code: "+pathCode.code) {
			t.Errorf("%s missing server rejection %s", pathCode.rel, pathCode.code)
		}
	}
}

// SIT-002.t5：既有 1v1 会话只读保留——SendMessage 契约显式拒绝 read_only。
func TestExistingDirectConversationBecomesReadOnlyOnBlockContract(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	ops := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml"))
	if !strings.Contains(ops, "accessMode=read_only") {
		t.Fatal("SendMessage must reject read_only conversations")
	}
	if !strings.Contains(ops, "CHAT.USER.blocked") {
		t.Fatal("SendMessage must list CHAT.USER.blocked as a server-side rejection")
	}
	fields := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/chat-service/contracts/chat/conversation/fields.yaml"))
	if !strings.Contains(fields, "read_only") {
		t.Fatal("conversation accessMode must declare read_only")
	}
}

// SIT-004.t1 / t2：CreateConversation 对 direct 校验 mutual 或 replied greeting。
func TestCreateConversationRequiresMutualOrRepliedGreeting(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	ops := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/chat-service/contracts/chat/conversation/operations.yaml"))
	for _, code := range []string{"CHAT.USER.not_mutual", "CHAT.USER.greeting_required", "CHAT.USER.blocked"} {
		if !strings.Contains(ops, code) {
			t.Errorf("CreateConversation operations missing gate error %s", code)
		}
	}
	if !strings.Contains(ops, "operation: CreateConversation") {
		t.Fatal("conversation operations must declare CreateConversation")
	}
}

// SIT-004.t3 / t4：SendMessage 服务端校验成员/拉黑/只读，不靠端侧按钮。
func TestSendMessageServerGateDoesNotRelyOnClientButtons(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	ops := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/chat-service/contracts/chat/message/operations.yaml"))
	for _, needle := range []string{
		"CHAT.USER.blocked",
		"accessMode=read_only",
		"conversation_member",
	} {
		if !strings.Contains(ops, needle) {
			t.Errorf("SendMessage gate missing %q", needle)
		}
	}
}

// SIT-004.t5 / t6：1v1 RTC 校验 mutual 且未 blocked，错误码来自 metadata。
func TestRTCOneToOneRequiresMutualAndNotBlocked(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	ops := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/rtc-service/contracts/rtc/call_session/operations.yaml"))
	errorsYAML := mustReadChat(t, filepath.Join(root,
		"quwoquan_service/services/rtc-service/contracts/rtc/call_session/errors.yaml"))
	for _, code := range []string{"RTC.USER.not_mutual", "RTC.USER.blocked"} {
		if !strings.Contains(errorsYAML, "code: "+code) {
			t.Errorf("rtc errors missing %s", code)
		}
		if !strings.Contains(ops, code) {
			t.Errorf("rtc operations must reference %s", code)
		}
	}
}

// SIT-004.t7：端侧错误态与服务端错误语义同源（dart_const 绑定）。
func TestClientErrorStatesHomologousWithServerCodes(t *testing.T) {
	t.Parallel()

	root := chatSitRepoRoot(t)
	for _, rel := range []string{
		"quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml",
		"quwoquan_service/services/rtc-service/contracts/rtc/call_session/errors.yaml",
	} {
		body := mustReadChat(t, filepath.Join(root, rel))
		for _, code := range []string{"not_mutual", "blocked"} {
			if !strings.Contains(body, code) {
				t.Errorf("%s missing %s", rel, code)
			}
		}
		if !strings.Contains(body, "dart_const:") {
			t.Errorf("%s must bind dart_const so client error UI stays homologous", rel)
		}
	}
}

func mustReadChat(t *testing.T, path string) string {
	t.Helper()
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(body)
}

func chatSitRepoRoot(t *testing.T) string {
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
