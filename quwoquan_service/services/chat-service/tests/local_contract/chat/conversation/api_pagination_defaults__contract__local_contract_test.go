// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
package local_contract

import (
	"fmt"
	"os"
	"path/filepath"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestAppExposedChatLimitDefaultsAreOwnedByEachOperation(t *testing.T) {
	t.Parallel()

	tests := []struct {
		object        string
		operation     string
		requestEntity string
		defaultItems  int
		maximumItems  int
	}{
		{
			object: "chat_inbox_view", operation: "ListInbox",
			requestEntity: "ChatListInboxQuery", defaultItems: 50, maximumItems: 50,
		},
		{
			object: "conversation_membership", operation: "ListMembers",
			requestEntity: "ChatListConversationMembersQuery", defaultItems: 20, maximumItems: 50,
		},
		{
			object: "message", operation: "SyncMessages",
			requestEntity: "ChatSyncMessagesQuery", defaultItems: 500, maximumItems: 500,
		},
		{
			object: "message", operation: "ListConversationAssets",
			requestEntity: "ChatListConversationAssetsQuery", defaultItems: 60, maximumItems: 200,
		},
		{
			object: "conversation", operation: "ListContacts",
			requestEntity: "ChatListContactsQuery", defaultItems: 20, maximumItems: 100,
		},
		{
			object: "conversation", operation: "ListGroupCandidates",
			requestEntity: "ChatListGroupCandidatesQuery", defaultItems: 100, maximumItems: 100,
		},
		{
			object: "conversation", operation: "ListSelectableGroupConversations",
			requestEntity: "ChatListSelectableGroupConversationsQuery", defaultItems: 50, maximumItems: 50,
		},
		{
			object: "conversation", operation: "ListSelectableGroupContactMembers",
			requestEntity: "ChatListSelectableGroupContactMembersQuery", defaultItems: 100, maximumItems: 100,
		},
	}

	for _, test := range tests {
		test := test
		t.Run(test.operation, func(t *testing.T) {
			t.Parallel()
			objectDir := filepath.Join(
				chatServiceContractRoot(t), "contracts", "chat", test.object,
			)
			operation := readChatPaginationOperation(t, filepath.Join(objectDir, "operations.yaml"), test.operation)
			if operation.RequestEntity != test.requestEntity {
				t.Fatalf("%s request_entity=%q want %q", test.operation, operation.RequestEntity, test.requestEntity)
			}
			if operation.Pagination.DefaultItems != test.defaultItems ||
				operation.Pagination.MaximumItems != test.maximumItems {
				t.Fatalf(
					"%s pagination=%+v want default=%d maximum=%d",
					test.operation, operation.Pagination, test.defaultItems, test.maximumItems,
				)
			}
			clientDefault := readChatLimitClientDefault(
				t, filepath.Join(objectDir, "fields.yaml"), test.requestEntity,
			)
			if clientDefault != fmt.Sprint(test.defaultItems) {
				t.Fatalf(
					"%s limit client_default=%q want %d",
					test.requestEntity, clientDefault, test.defaultItems,
				)
			}
		})
	}
}

type chatPaginationOperation struct {
	Operation     string `yaml:"operation"`
	RequestEntity string `yaml:"request_entity"`
	Pagination    struct {
		DefaultItems int `yaml:"default_items"`
		MaximumItems int `yaml:"maximum_items"`
	} `yaml:"pagination"`
}

func readChatPaginationOperation(t *testing.T, path, operationID string) chatPaginationOperation {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		APIRoutes []chatPaginationOperation `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	for _, operation := range document.APIRoutes {
		if operation.Operation == operationID {
			return operation
		}
	}
	t.Fatalf("operation %s not found in %s", operationID, path)
	return chatPaginationOperation{}
}

func readChatLimitClientDefault(t *testing.T, path, entityName string) string {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		Types map[string]struct {
			Fields []struct {
				Name          string `yaml:"name"`
				ClientDefault any    `yaml:"client_default"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	entity, found := document.Types[entityName]
	if !found {
		t.Fatalf("request entity %s not found in %s", entityName, path)
	}
	for _, field := range entity.Fields {
		if field.Name == "limit" {
			return fmt.Sprint(field.ClientDefault)
		}
	}
	t.Fatalf("request entity %s has no limit field", entityName)
	return ""
}
