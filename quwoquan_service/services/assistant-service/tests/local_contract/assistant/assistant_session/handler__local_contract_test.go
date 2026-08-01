package local_contract

import "testing"

// TestAssistantSessionHandler validates the contract at the public assistant application boundary.
func TestAssistantSessionHandlerApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
