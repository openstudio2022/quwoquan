// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
package local_contract

import (
	"strings"
	"testing"
	"time"

	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
)

func TestFederatedPhoneBindingTicketBindsProviderIdentityAndFullContext(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
	ticket, err := bindingmodel.RestoreFederatedPhoneBindingTicket(
		bindingmodel.FederatedPhoneBindingTicket{
			ID:               "fbt_ticket-1",
			Hash:             strings.Repeat("a", 64),
			Provider:         bindingmodel.FederatedProviderSlotA,
			CredentialType:   bindingmodel.CredentialTypeFederatedSlotA,
			CredentialKey:    "wechat-subject-1",
			DeviceID:         "device-1",
			Platform:         "ios",
			AppVersion:       "1.0.0",
			AgreementVersion: "agreement-v1",
			PrivacyVersion:   "privacy-v1",
			Status:           bindingmodel.FederatedPhoneBindingTicketPending,
			ExpiresAt:        now.Add(3 * time.Minute),
			Version:          1,
			CreatedAt:        now,
			UpdatedAt:        now,
		},
	)
	if err != nil {
		t.Fatalf("restore valid ticket: %v", err)
	}
	if !ticket.MatchesContext(
		"device-1",
		"ios",
		"1.0.0",
		"agreement-v1",
		"privacy-v1",
	) {
		t.Fatal("exact authorization context must match")
	}
	if ticket.MatchesContext(
		"device-1",
		"ios",
		"1.0.1",
		"agreement-v1",
		"privacy-v1",
	) {
		t.Fatal("appVersion substitution must be rejected")
	}

	ticket.Provider = bindingmodel.FederatedProviderSlotC
	if _, err := bindingmodel.RestoreFederatedPhoneBindingTicket(ticket); err == nil {
		t.Fatal("provider and credential slot mismatch must be rejected")
	}
}

func TestFederatedPhoneBindingTicketRequiresOneTimeStateConsistency(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
	pending := bindingmodel.FederatedPhoneBindingTicket{
		ID:               "fbt_ticket-2",
		Hash:             strings.Repeat("b", 64),
		Provider:         bindingmodel.FederatedProviderSlotB,
		CredentialType:   bindingmodel.CredentialTypeFederatedSlotB,
		CredentialKey:    "alipay-subject-1",
		DeviceID:         "device-2",
		Platform:         "android",
		AppVersion:       "1.0.0",
		AgreementVersion: "agreement-v1",
		PrivacyVersion:   "privacy-v1",
		Status:           bindingmodel.FederatedPhoneBindingTicketPending,
		ExpiresAt:        now.Add(3 * time.Minute),
		Version:          1,
		CreatedAt:        now,
		UpdatedAt:        now,
	}
	consumedAt := now.Add(time.Minute)
	pending.ConsumedAt = &consumedAt
	if _, err := bindingmodel.RestoreFederatedPhoneBindingTicket(pending); err == nil {
		t.Fatal("pending ticket cannot carry consumedAt")
	}
	pending.Status = bindingmodel.FederatedPhoneBindingTicketConsumed
	pending.ConsumedAt = nil
	if _, err := bindingmodel.RestoreFederatedPhoneBindingTicket(pending); err == nil {
		t.Fatal("consumed ticket must carry consumedAt")
	}
}
