package local_contract

import "testing"

// TestAssistantSessionInfrastructureSearchclientClient validates the contract at the public assistant application boundary.
func TestAssistantSessionInfrastructureSearchclientClientApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
