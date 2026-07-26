package local_contract

import "testing"

// TestMigratedConversationLifecycle retains the contract at the public assistant application boundary.
func TestMigratedConversationLifecycleApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
