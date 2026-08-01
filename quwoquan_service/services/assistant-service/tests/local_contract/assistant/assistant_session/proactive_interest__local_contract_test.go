package local_contract

import "testing"

// TestAssistantSessionProactiveInterest validates the contract at the public assistant application boundary.
func TestAssistantSessionProactiveInterestApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
