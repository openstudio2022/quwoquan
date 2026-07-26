package local_contract

import "testing"

// TestMigratedToolCoordinator retains the contract at the public assistant application boundary.
func TestMigratedToolCoordinatorApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
