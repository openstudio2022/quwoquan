package local_contract

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

// TestConversationContactWireEnumsAreTyped 固定联系人候选行的 wire 强类型：
// source / relationState 不得回退成裸 string，必须绑定闭集枚举。
func TestConversationContactWireEnumsAreTyped(t *testing.T) {
	t.Parallel()

	contract := readConversationFieldsContract(t)
	for _, expected := range []struct {
		wireType string
		field    string
		enumRef  string
	}{
		{"ChatListSelectableGroupConversationsQuery", "source", "SelectableGroupConversationSource"},
		{"GroupCandidateRow", "source", "ChatContactSource"},
		{"GroupCandidateRow", "relationState", "RelationshipState"},
		{"SelectableGroupContactMemberRow", "source", "ChatContactSource"},
		{"SelectableGroupContactMemberRow", "relationState", "RelationshipState"},
	} {
		wireType, declared := contract.Types[expected.wireType]
		if !declared {
			t.Fatalf("conversation/fields.yaml must declare %s", expected.wireType)
		}
		found := false
		for _, field := range wireType.Fields {
			if field.Name != expected.field {
				continue
			}
			found = true
			if field.Type != "enum" || field.EnumRef != expected.enumRef {
				t.Fatalf(
					"%s.%s must be enum %s, got type=%q enum_ref=%q",
					expected.wireType, expected.field, expected.enumRef, field.Type, field.EnumRef,
				)
			}
		}
		if !found {
			t.Fatalf("%s.%s is missing", expected.wireType, expected.field)
		}
	}
}

// TestChatContactSourceMatchesNormalizerDomain 固定 ChatContactSource 的真相源：
// 契约取值必须与 normalizeContactSource / normalizeSocialSource 的闭集逐值一致。
func TestChatContactSourceMatchesNormalizerDomain(t *testing.T) {
	t.Parallel()

	contract := readConversationFieldsContract(t)
	declared := append([]string(nil), contract.Enums["ChatContactSource"].Values...)
	if len(declared) == 0 {
		t.Fatal("conversation/fields.yaml must own ChatContactSource")
	}
	sort.Strings(declared)

	root := chatServiceContractRoot(t)
	for _, normalizer := range []struct {
		file string
		fn   string
	}{
		{
			filepath.Join(root, "internal", "chat", "conversation", "application",
				"member_contact_service.go"),
			"normalizeContactSource",
		},
		{
			filepath.Join(root, "internal", "chat", "conversation", "adapters", "inbound", "http",
				"social_contact_resolver_client.go"),
			"normalizeSocialSource",
		},
	} {
		implemented := readNormalizerCaseValues(t, normalizer.file, normalizer.fn)
		if strings.Join(implemented, ",") != strings.Join(declared, ",") {
			t.Fatalf(
				"%s accepts %v but ChatContactSource declares %v",
				normalizer.fn, implemented, declared,
			)
		}
	}
}

// TestSelectableGroupConversationSourceMatchesQueryGuard 固定来源过滤闭集：
// 契约取值必须与 MemberService.ListSelectableGroupConversations 的入参校验一致。
func TestSelectableGroupConversationSourceMatchesQueryGuard(t *testing.T) {
	t.Parallel()

	contract := readConversationFieldsContract(t)
	declared := append([]string(nil), contract.Enums["SelectableGroupConversationSource"].Values...)
	if len(declared) == 0 {
		t.Fatal("conversation/fields.yaml must own SelectableGroupConversationSource")
	}
	sort.Strings(declared)

	guard := readChatContract(t, filepath.Join(
		chatServiceContractRoot(t), "internal", "chat", "conversation", "application",
		"selectable_group_service.go",
	))
	for _, value := range declared {
		if !strings.Contains(guard, `source != "`+value+`"`) {
			t.Fatalf("ListSelectableGroupConversations does not accept source %q", value)
		}
	}
	rejected := regexp.MustCompile(`source != "([a-z_]+)"`).FindAllStringSubmatch(guard, -1)
	accepted := make([]string, 0, len(rejected))
	for _, match := range rejected {
		accepted = append(accepted, match[1])
	}
	sort.Strings(accepted)
	if strings.Join(accepted, ",") != strings.Join(declared, ",") {
		t.Fatalf(
			"query guard accepts %v but SelectableGroupConversationSource declares %v",
			accepted, declared,
		)
	}
}

// TestContactRelationStateStaysWithinSharedDomain 固定 relationState 复用共享值域：
// 归一化实现的取值必须是 _shared RelationshipState 的子集，避免第二套近似枚举。
func TestContactRelationStateStaysWithinSharedDomain(t *testing.T) {
	t.Parallel()

	shared := readSharedRelationshipStates(t)
	implemented := readNormalizerCaseValues(t,
		filepath.Join(chatServiceContractRoot(t), "internal", "chat", "conversation",
			"adapters", "inbound", "http", "social_contact_resolver_client.go"),
		"normalizeSocialRelationState",
	)
	if len(implemented) == 0 {
		t.Fatal("normalizeSocialRelationState must declare a closed value set")
	}
	for _, value := range implemented {
		found := false
		for _, candidate := range shared {
			if candidate == value {
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("relation state %q is not part of the shared RelationshipState domain", value)
		}
	}
}

type conversationFieldsContract struct {
	Types map[string]struct {
		Fields []struct {
			Name    string `yaml:"name"`
			Type    string `yaml:"type"`
			EnumRef string `yaml:"enum_ref"`
		} `yaml:"fields"`
	} `yaml:"types"`
	Enums map[string]struct {
		Values []string `yaml:"values"`
	} `yaml:"enums"`
}

func readConversationFieldsContract(t *testing.T) conversationFieldsContract {
	t.Helper()
	path := filepath.Join(
		chatServiceContractRoot(t), "contracts", "chat", "conversation", "fields.yaml",
	)
	var contract conversationFieldsContract
	if err := yaml.Unmarshal([]byte(readChatContract(t, path)), &contract); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return contract
}

// readNormalizerCaseValues 抽取归一化函数首个 case 分支的字面量闭集。
func readNormalizerCaseValues(t *testing.T, file string, fn string) []string {
	t.Helper()
	raw, err := os.ReadFile(file)
	if err != nil {
		t.Fatalf("read %s: %v", file, err)
	}
	body := string(raw)
	start := strings.Index(body, "func "+fn+"(")
	if start < 0 {
		t.Fatalf("%s does not declare %s", file, fn)
	}
	body = body[start:]
	caseStart := strings.Index(body, "\tcase ")
	if caseStart < 0 {
		t.Fatalf("%s has no case branch", fn)
	}
	body = body[caseStart:]
	lineEnd := strings.Index(body, ":\n")
	if lineEnd < 0 {
		t.Fatalf("%s has a malformed case branch", fn)
	}
	values := regexp.MustCompile(`"([a-z_]+)"`).FindAllStringSubmatch(body[:lineEnd], -1)
	accepted := make([]string, 0, len(values))
	for _, match := range values {
		accepted = append(accepted, match[1])
	}
	sort.Strings(accepted)
	return accepted
}

func readSharedRelationshipStates(t *testing.T) []string {
	t.Helper()
	path := filepath.Clean(filepath.Join(
		chatServiceContractRoot(t), "..", "..", "contracts", "metadata", "_shared", "types.yaml",
	))
	var shared struct {
		Enums map[string][]string `yaml:"enums"`
	}
	if err := yaml.Unmarshal([]byte(readChatContract(t, path)), &shared); err != nil {
		t.Fatalf("decode shared types: %v", err)
	}
	values, declared := shared.Enums["RelationshipState"]
	if !declared {
		t.Fatal("_shared/types.yaml must declare RelationshipState")
	}
	return values
}
