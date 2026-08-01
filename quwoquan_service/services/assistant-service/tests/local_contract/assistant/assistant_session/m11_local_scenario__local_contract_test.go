package local_contract

import "testing"

// TestAssistantSessionM11LocalScenario validates the contract at the public assistant application boundary.
func TestAssistantSessionM11LocalScenarioApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
