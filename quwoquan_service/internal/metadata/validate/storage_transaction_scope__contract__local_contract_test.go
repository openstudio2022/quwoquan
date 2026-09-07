package validate

import (
	"os"
	"path/filepath"
	"testing"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageTransactionScopeValidatesLocalAndSiblingCollections(t *testing.T) {
	root := t.TempDir()
	writeStorageFixture(t, root, "integration/external_integration/connector_connection", `backend: mongodb
role: authoritative
collections:
  connector_connections: {entity: ConnectorConnection, role: authoritative}
transaction:
  scope: [connector_connections]
  isolation: mongo_transaction
  guarantees: [connection_and_invocation_atomicity]
  participants:
  - object: connector_invocation
    collections: [connector_invocations]
`)
	writeStorageFixture(t, root, "integration/external_integration/connector_invocation", `backend: mongodb
role: authoritative
collections:
  connector_invocations: {entity: ConnectorInvocation, role: authoritative}
`)
	issues, err := storageTransactionScopeIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("canonical cross-object transaction rejected: %+v", issues)
	}

	writeStorageFixture(t, root, "integration/external_integration/connector_connection", `backend: mongodb
role: authoritative
collections:
  connector_connections: {entity: ConnectorConnection, role: authoritative}
transaction:
  scope: [connector_invocations]
  isolation: mongo_transaction
  guarantees: [connection_and_invocation_atomicity]
  participants:
  - object: connector_invocation
    collections: [missing_invocation_collection]
`)
	issues, err = storageTransactionScopeIssues(root)
	if err != nil {
		t.Fatal(err)
	}
	if !transactionScopeHasIssueCode(issues, "CONTRACT.STORAGE.TRANSACTION_SCOPE_UNKNOWN") ||
		!transactionScopeHasIssueCode(issues, "CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_COLLECTION_UNKNOWN") {
		t.Fatalf("invalid transaction resources were not rejected: %+v", issues)
	}
}

func writeStorageFixture(t *testing.T, root, objectPath, document string) {
	t.Helper()
	directory := filepath.Join(root, filepath.FromSlash(objectPath))
	if err := os.MkdirAll(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(directory, "storage.yaml"), []byte(document), 0o644); err != nil {
		t.Fatal(err)
	}
}

func transactionScopeHasIssueCode(issues []Issue, code string) bool {
	for _, issue := range issues {
		if issue.Code == code {
			return true
		}
	}
	return false
}
