package local_contract

import "testing"

// TestAssistantSessionService validates the contract at the public assistant application boundary.
func TestAssistantSessionServiceApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
