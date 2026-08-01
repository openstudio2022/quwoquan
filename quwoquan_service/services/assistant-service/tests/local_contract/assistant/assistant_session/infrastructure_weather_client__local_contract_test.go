package local_contract

import "testing"

// TestAssistantSessionInfrastructureWeatherClient validates the contract at the public assistant application boundary.
func TestAssistantSessionInfrastructureWeatherClientApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
