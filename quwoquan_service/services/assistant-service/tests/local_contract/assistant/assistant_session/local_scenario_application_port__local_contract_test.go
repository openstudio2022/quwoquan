package local_contract

import "testing"

// TestAssistantSessionLocalScenarioApplicationPort validates the contract at the public assistant application boundary.
func TestAssistantSessionLocalScenarioApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
