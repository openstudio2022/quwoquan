// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	"strings"
	"testing"

	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
)

func TestFederatedLoginOutcomeHasExactlyTwoExclusiveStates(t *testing.T) {
	t.Parallel()

	session := &sessionapp.AuthSessionGrant{OwnerID: "owner-1"}
	authenticated, err := sessionapp.NewAuthenticatedFederatedLogin(session)
	if err != nil {
		t.Fatalf("authenticated outcome: %v", err)
	}
	authenticatedJSON, err := json.Marshal(authenticated)
	if err != nil {
		t.Fatalf("marshal authenticated outcome: %v", err)
	}
	if strings.Contains(string(authenticatedJSON), "bindingTicket") ||
		strings.Contains(string(authenticatedJSON), "provider") ||
		strings.Contains(string(authenticatedJSON), "expiresInSeconds") {
		t.Fatalf("authenticated outcome leaked binding-only fields: %s", authenticatedJSON)
	}

	pending, err := sessionapp.NewPhoneBindingRequiredFederatedLogin(
		"fb_opaque-ticket",
		"federated_slot_a",
		180,
	)
	if err != nil {
		t.Fatalf("phone-binding outcome: %v", err)
	}
	pendingJSON, err := json.Marshal(pending)
	if err != nil {
		t.Fatalf("marshal phone-binding outcome: %v", err)
	}
	if strings.Contains(string(pendingJSON), "session") {
		t.Fatalf("phone-binding outcome leaked a session field: %s", pendingJSON)
	}
}

func TestFederatedLoginOutcomeRejectsMixedOrUnsupportedState(t *testing.T) {
	t.Parallel()

	invalid := []sessionapp.FederatedLoginOutcome{
		{Status: sessionapp.FederatedLoginAuthenticated},
		{
			Status:        sessionapp.FederatedLoginAuthenticated,
			Session:       &sessionapp.AuthSessionGrant{OwnerID: "owner-1"},
			BindingTicket: "fb_mixed",
		},
		{
			Status:           sessionapp.FederatedLoginPhoneBindingRequired,
			BindingTicket:    "fb_pending",
			Provider:         "apple",
			ExpiresInSeconds: 180,
		},
		{Status: "cancelled"},
	}
	for _, outcome := range invalid {
		if err := outcome.Validate(); err == nil {
			t.Fatalf("invalid outcome was accepted: %+v", outcome)
		}
	}
}
