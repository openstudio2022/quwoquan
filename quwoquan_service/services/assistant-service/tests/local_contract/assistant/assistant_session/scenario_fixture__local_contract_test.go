package local_contract

import "testing"

// TestAssistantSessionScenarioFixture validates the contract at the public assistant application boundary.
func TestAssistantSessionScenarioFixtureApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
