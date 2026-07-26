package local_contract

import "testing"

// TestMigratedM11LocalScenario retains the contract at the public assistant application boundary.
func TestMigratedM11LocalScenarioApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
