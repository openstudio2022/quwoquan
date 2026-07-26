package local_contract

import "testing"

// TestMigratedInfrastructureWeatherClient retains the contract at the public assistant application boundary.
func TestMigratedInfrastructureWeatherClientApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
