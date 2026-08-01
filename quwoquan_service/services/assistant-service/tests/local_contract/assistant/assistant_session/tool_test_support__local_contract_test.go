package local_contract

import "testing"

// TestAssistantSessionToolTestSupport validates the contract at the public assistant application boundary.
func TestAssistantSessionToolTestSupportApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
