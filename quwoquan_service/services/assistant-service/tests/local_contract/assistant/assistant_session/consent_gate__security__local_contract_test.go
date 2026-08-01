package local_contract

import "testing"

// TestAssistantSessionConsentGateSecurity validates behavior through the public assistant application port.
func TestAssistantSessionConsentGateSecurityApplicationPort(t *testing.T) {
	assertAssistantApplicationPort(t)
}
