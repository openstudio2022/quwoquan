package local_contract

import "testing"

// TestAssistantSessionToolCoordinator validates the contract at the public assistant application boundary.
func TestAssistantSessionToolCoordinatorApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
