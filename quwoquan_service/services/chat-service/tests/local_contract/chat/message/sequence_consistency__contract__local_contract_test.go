// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
package local_contract

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestMessageSequenceConsistencyContractMatchesMongoCommitBoundary(t *testing.T) {
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	serviceRoot := filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
	objectRoot := filepath.Join(serviceRoot, "contracts", "chat", "message")

	operationsData, err := os.ReadFile(filepath.Join(objectRoot, "operations.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var operations struct {
		APIRoutes []struct {
			Operation   string `yaml:"operation"`
			Consistency struct {
				AtomicCommit bool   `yaml:"atomic_commit"`
				Arbitration  string `yaml:"arbitration"`
			} `yaml:"consistency"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(operationsData, &operations); err != nil {
		t.Fatal(err)
	}
	byOperation := make(map[string]struct {
		AtomicCommit bool
		Arbitration  string
	}, len(operations.APIRoutes))
	for _, route := range operations.APIRoutes {
		byOperation[route.Operation] = struct {
			AtomicCommit bool
			Arbitration  string
		}{route.Consistency.AtomicCommit, route.Consistency.Arbitration}
	}
	for _, operation := range []string{"SendMessage", "SendAssistantDeliveryMessage"} {
		consistency, found := byOperation[operation]
		if !found {
			t.Fatalf("message sequence command %s is missing", operation)
		}
		if !consistency.AtomicCommit || consistency.Arbitration != "unique_winner" {
			t.Fatalf("message sequence command %s consistency=%+v", operation, consistency)
		}
	}

	storageData, err := os.ReadFile(filepath.Join(objectRoot, "storage.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var storage struct {
		Transaction struct {
			Scope      []string `yaml:"scope"`
			Isolation  string   `yaml:"isolation"`
			Guarantees []string `yaml:"guarantees"`
			Mechanism  string   `yaml:"mechanism"`
		} `yaml:"transaction"`
	}
	if err := yaml.Unmarshal(storageData, &storage); err != nil {
		t.Fatal(err)
	}
	assertStringSet(t, storage.Transaction.Scope, []string{
		"messages",
		"messages_command_receipts",
		"messages_sequences",
		"messages_outbox",
		"messages_outbox_sequences",
	})
	assertStringSet(t, storage.Transaction.Guarantees, []string{
		"per_conversation_seq_strictly_unique_monotonic",
		"message_receipt_outbox_atomic_commit",
		"same_client_message_command_idempotent_replay",
		"conflicting_client_message_command_fail_closed",
		"message_outbox_sequence_strictly_unique_monotonic",
	})
	if storage.Transaction.Isolation != "mongo_transaction" ||
		storage.Transaction.Mechanism != "conditional_update" {
		t.Fatalf("message transaction drifted: %+v", storage.Transaction)
	}
}

func assertStringSet(t *testing.T, got, want []string) {
	t.Helper()
	gotSet := make(map[string]struct{}, len(got))
	for _, value := range got {
		gotSet[value] = struct{}{}
	}
	if len(gotSet) != len(want) {
		t.Fatalf("string set=%v, want=%v", got, want)
	}
	for _, value := range want {
		if _, found := gotSet[value]; !found {
			t.Fatalf("string set=%v is missing %q", got, value)
		}
	}
}
