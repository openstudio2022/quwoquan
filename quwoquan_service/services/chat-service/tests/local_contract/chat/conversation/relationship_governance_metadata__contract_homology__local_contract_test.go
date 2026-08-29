// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-005
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-005.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-005.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-005.t3
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// SIT-005.t1：旧关系等级字段不得存活在 metadata、codegen 产物、Go struct 或 Dart DTO 里。
// 四类载体一起扫：只清其中一类时，剩下三类会成为悄悄复活的入口。
func TestNoLegacyRelationshipTierAcrossMetadataAndBothSides(t *testing.T) {
	t.Parallel()

	root := governanceRepositoryRoot(t)
	forbidden := []string{
		"relationshipTier", "relationship_tier", "RelationshipTier",
		"friendLevel", "friend_level", "FriendLevel",
		"intimacyLevel", "intimacy_level", "IntimacyLevel",
		"relationLevel", "relation_level", "RelationLevel",
	}
	carriers := map[string][]string{
		"metadata": {"quwoquan_service/contracts/metadata"},
		"contracts": {
			"quwoquan_service/services/chat-service/contracts",
			"quwoquan_service/services/rtc-service/contracts",
			"quwoquan_service/services/user-service/contracts/relationship",
		},
		"go-struct": {
			"quwoquan_service/services/chat-service/internal/chat/conversation",
			"quwoquan_service/services/user-service/internal/relationship",
		},
		"dart-dto": {
			"quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/chat",
			"quwoquan_app/packages/quwoquan_cloud_contracts/lib/src/user",
		},
	}

	for carrier, bases := range carriers {
		scanned := 0
		for _, relative := range bases {
			base := filepath.Join(root, relative)
			if _, err := os.Stat(base); err != nil {
				continue
			}
			err := filepath.Walk(base, func(path string, info os.FileInfo, err error) error {
				if err != nil || info.IsDir() {
					return err
				}
				switch filepath.Ext(path) {
				case ".yaml", ".yml", ".json", ".go", ".dart":
				default:
					return nil
				}
				body, readErr := os.ReadFile(path)
				if readErr != nil {
					return readErr
				}
				scanned++
				for _, name := range forbidden {
					if strings.Contains(string(body), name) {
						t.Errorf("[%s] %s still carries legacy relationship tier field %q", carrier, path, name)
					}
				}
				return nil
			})
			if err != nil {
				t.Fatalf("walk %s: %v", base, err)
			}
		}
		if scanned == 0 {
			t.Fatalf("carrier %s scanned no files; the guard would pass vacuously", carrier)
		}
	}
}

// SIT-005.t2：三条受门禁保护的操作各自都要有结构化的关系/拉黑错误码。
// 少任何一条，对应链路就只能靠端侧按钮兜底，服务端门禁形同虚设。
func TestRelationshipAndBlockedErrorCodesExistForEveryGuardedOperation(t *testing.T) {
	t.Parallel()

	root := governanceRepositoryRoot(t)
	for _, expected := range []struct {
		operation string
		errorsRel string
		codes     []string
	}{
		{
			operation: "CreateConversation / SendMessage",
			errorsRel: "quwoquan_service/services/chat-service/contracts/chat/conversation/errors.yaml",
			codes: []string{
				"CHAT.USER.not_mutual",
				"CHAT.USER.greeting_required",
				"CHAT.USER.blocked",
			},
		},
		{
			operation: "RTC 1v1",
			errorsRel: "quwoquan_service/services/rtc-service/contracts/rtc/call_session/errors.yaml",
			codes: []string{
				"RTC.USER.not_mutual",
				"RTC.USER.blocked",
			},
		},
	} {
		body, err := os.ReadFile(filepath.Join(root, expected.errorsRel))
		if err != nil {
			t.Fatalf("read %s: %v", expected.errorsRel, err)
		}
		source := string(body)
		for _, code := range expected.codes {
			if !strings.Contains(source, "code: "+code) {
				t.Errorf("%s missing structured error %q for %s", expected.errorsRel, code, expected.operation)
				continue
			}
			// 有错误码还不够：端侧必须能拿到常量，否则映射只能靠字符串硬编码。
			if !strings.Contains(source, "dart_const:") {
				t.Errorf("%s declares %q without any dart_const binding", expected.errorsRel, code)
			}
		}
	}
}

// SIT-005.t3：四个事件的载荷字段可被端云测试引用，即字段在契约里逐个具名声明。
func TestGovernanceEventsExposeReferenceablePayloadFields(t *testing.T) {
	t.Parallel()

	root := governanceRepositoryRoot(t)
	for _, expected := range []struct {
		eventsRel string
		event     string
		fields    []string
	}{
		{
			eventsRel: "quwoquan_service/services/user-service/contracts/relationship/persona_relationship/events.yaml",
			event:     "PersonaBlocked",
			fields:    []string{"pairId", "sourcePersonaId", "targetPersonaId", "version", "occurredAt"},
		},
		{
			eventsRel: "quwoquan_service/services/user-service/contracts/relationship/persona_relationship/events.yaml",
			event:     "PersonaUnblocked",
			fields:    []string{"pairId", "sourcePersonaId", "targetPersonaId", "version", "occurredAt"},
		},
		{
			eventsRel: "quwoquan_service/services/user-service/contracts/relationship/greeting_request/events.yaml",
			event:     "GreetingRequestReplied",
			fields:    []string{"id", "requesterPersonaId", "targetPersonaId", "promotedConversationId"},
		},
		{
			eventsRel: "quwoquan_service/services/chat-service/contracts/chat/message/events.yaml",
			event:     "MessageSent",
			fields:    []string{"conversationId"},
		},
	} {
		declared := governanceEventPayloadFields(t, filepath.Join(root, expected.eventsRel), expected.event)
		if declared == nil {
			t.Errorf("%s does not declare event %s", expected.eventsRel, expected.event)
			continue
		}
		present := make(map[string]struct{}, len(declared))
		for _, field := range declared {
			present[field] = struct{}{}
		}
		for _, field := range expected.fields {
			if _, ok := present[field]; !ok {
				t.Errorf("%s.%s payload has no referenceable field %q (declared=%v)",
					expected.event, expected.eventsRel, field, declared)
			}
		}
	}
}

// governanceEventPayloadFields 读契约本身而不是搜字符串：
// payload_fields 是结构化列表，逐键解析才能区分「字段真的在场」和「名字恰好出现在描述里」。
func governanceEventPayloadFields(t *testing.T, path, eventName string) []string {
	t.Helper()
	body, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	type eventDecl struct {
		Name          string   `yaml:"name"`
		PayloadFields []string `yaml:"payload_fields"`
	}
	var asList []eventDecl
	if err := yaml.Unmarshal(body, &asList); err == nil && len(asList) > 0 {
		for _, decl := range asList {
			if decl.Name == eventName {
				return decl.PayloadFields
			}
		}
	}
	var wrapped struct {
		Events []eventDecl `yaml:"events"`
	}
	if err := yaml.Unmarshal(body, &wrapped); err != nil {
		t.Fatalf("parse %s: %v", path, err)
	}
	for _, decl := range wrapped.Events {
		if decl.Name == eventName {
			return decl.PayloadFields
		}
	}
	return nil
}

func governanceRepositoryRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "specs", "feature-tree")); statErr == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repository root not found from test working directory")
		}
		dir = parent
	}
}
