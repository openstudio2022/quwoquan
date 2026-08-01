package local_contract

import "testing"

// TestAssistantSessionInfrastructurePublicsearchClient validates the contract at the public assistant application boundary.
func TestAssistantSessionInfrastructurePublicsearchClientApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
