package local_contract

import "testing"

// TestMigratedIntersectionReminderService retains the contract at the public assistant application boundary.
func TestMigratedIntersectionReminderServiceApplicationPort(t *testing.T) {
	assertMigratedAssistantApplicationPort(t)
}
