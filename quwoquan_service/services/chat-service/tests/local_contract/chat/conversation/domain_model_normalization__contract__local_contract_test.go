package local_contract

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"

	"gopkg.in/yaml.v3"
)

func TestConversationSourceContractRemovesDerivedBindingSemantics(t *testing.T) {
	t.Parallel()

	root := chatServiceContractRoot(t)
	paths := []string{
		filepath.Join(root, "contracts", "chat", "conversation", "fields.yaml"),
		filepath.Join(root, "contracts", "chat", "conversation", "projections", "chat_conversation.yaml"),
		filepath.Join(root, "contracts", "chat", "conversation", "projections", "group_home.yaml"),
	}
	for _, path := range paths {
		contract := readChatContract(t, path)
		for _, retired := range []string{"bindingType", "lifecyclePolicy"} {
			if strings.Contains(contract, retired) {
				t.Fatalf("%s retains derived conversation field %s", path, retired)
			}
		}
	}

	raw, err := json.Marshal(conversationmodel.Conversation{OriginType: "direct_init"})
	if err != nil {
		t.Fatalf("marshal Conversation: %v", err)
	}
	if strings.Contains(string(raw), "bindingType") || strings.Contains(string(raw), "lifecyclePolicy") {
		t.Fatalf("Conversation implementation emits retired source semantics: %s", raw)
	}
}

func TestConversationPreviewTypesReferenceCanonicalMessageType(t *testing.T) {
	t.Parallel()

	root := chatServiceContractRoot(t)
	for _, path := range []string{
		filepath.Join(root, "contracts", "chat", "conversation", "fields.yaml"),
		filepath.Join(root, "contracts", "chat", "chat_inbox_view", "fields.yaml"),
		filepath.Join(root, "contracts", "chat", "conversation", "projections", "chat_conversation.yaml"),
		filepath.Join(root, "contracts", "chat", "chat_inbox_view", "projections", "chat_inbox.yaml"),
	} {
		contract := readChatContract(t, path)
		if !strings.Contains(contract, "name: lastMessageType") ||
			!strings.Contains(contract, "enum_ref: MessageType") {
			t.Fatalf("%s does not bind lastMessageType to MessageType", path)
		}
	}
}

func TestMessageCardIsTypedOwnedValue(t *testing.T) {
	t.Parallel()

	root := chatServiceContractRoot(t)
	messageFields := readChatContract(t, filepath.Join(
		root, "contracts", "chat", "message", "fields.yaml",
	))
	var messageContract struct {
		Fields []struct {
			Name string `yaml:"name"`
			Type string `yaml:"type"`
			Role string `yaml:"role"`
		} `yaml:"fields"`
		ValueObjects map[string]struct {
			Fields []struct {
				Name string `yaml:"name"`
				Type string `yaml:"type"`
			} `yaml:"fields"`
		} `yaml:"value_objects"`
		Types map[string]any `yaml:"types"`
	}
	if err := yaml.Unmarshal([]byte(messageFields), &messageContract); err != nil {
		t.Fatalf("decode Message fields contract: %v", err)
	}
	cardOwned := false
	for _, field := range messageContract.Fields {
		if field.Name == "card" && field.Type == "MessageCard" && field.Role == "owned_value" {
			cardOwned = true
			break
		}
	}
	if !cardOwned {
		t.Fatal("Message.card is not bound to the owned MessageCard value object")
	}
	card, cardDeclared := messageContract.ValueObjects["MessageCard"]
	if !cardDeclared {
		t.Fatal("MessageCard must be declared in value_objects")
	}
	attributeDeclared := false
	for _, field := range card.Fields {
		if field.Name == "attributes" && field.Type == "[]MessageCardAttribute" {
			attributeDeclared = true
			break
		}
	}
	if !attributeDeclared {
		t.Fatal("MessageCard.attributes must reference the owned MessageCardAttribute value object")
	}
	if _, ok := messageContract.ValueObjects["MessageCardAttribute"]; !ok {
		t.Fatal("MessageCardAttribute must be declared in value_objects")
	}
	for _, name := range []string{"MessageCard", "MessageCardAttribute"} {
		if _, leaked := messageContract.Types[name]; leaked {
			t.Fatalf("owned value object %s leaked into transport types", name)
		}
	}

}

func chatServiceContractRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func readChatContract(t *testing.T, path string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(raw)
}
