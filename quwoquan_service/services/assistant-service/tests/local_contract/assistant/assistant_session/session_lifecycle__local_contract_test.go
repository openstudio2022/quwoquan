package local_contract

import "testing"

// TestAssistantSessionSessionLifecycle validates the contract at the public assistant application boundary.
func TestAssistantSessionSessionLifecycleApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
