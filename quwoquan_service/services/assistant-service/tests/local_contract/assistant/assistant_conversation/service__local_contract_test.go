package local_contract

import "testing"

// TestMigratedService retains the contract at the public assistant application boundary.
func TestMigratedServiceApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
