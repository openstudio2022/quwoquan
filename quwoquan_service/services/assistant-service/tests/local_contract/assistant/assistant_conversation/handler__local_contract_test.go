package local_contract

import "testing"

// TestMigratedHandler retains the contract at the public assistant application boundary.
func TestMigratedHandlerApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
