package local_contract

import "testing"

// TestAssistantSessionIntersectionReminderService validates the contract at the public assistant application boundary.
func TestAssistantSessionIntersectionReminderServiceApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
