package local_contract

import "testing"

// TestMigratedScenarioFixture retains the contract at the public assistant application boundary.
func TestMigratedScenarioFixtureApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
