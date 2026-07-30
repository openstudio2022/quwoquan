package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var ErrInvalidFederatedPhoneBindingTicket = errors.New(
	"federated phone binding ticket is invalid",
)

type FederatedProvider string

const (
	FederatedProviderSlotA FederatedProvider = "federated_slot_a"
	FederatedProviderSlotB FederatedProvider = "federated_slot_b"
	FederatedProviderSlotC FederatedProvider = "federated_slot_c"
)

func (provider FederatedProvider) Valid() bool {
	switch provider {
	case FederatedProviderSlotA, FederatedProviderSlotB, FederatedProviderSlotC:
		return true
	default:
		return false
	}
}

type FederatedPhoneBindingTicketStatus string

const (
	FederatedPhoneBindingTicketPending  FederatedPhoneBindingTicketStatus = "pending"
	FederatedPhoneBindingTicketConsumed FederatedPhoneBindingTicketStatus = "consumed"
)

type FederatedPhoneBindingTicket struct {
	ID               string
	Hash             string
	Provider         FederatedProvider
	CredentialType   CredentialType
	CredentialKey    string
	DisplayName      string
	AvatarURL        string
	DeviceID         string
	Platform         string
	AppVersion       string
	AgreementVersion string
	PrivacyVersion   string
	Status           FederatedPhoneBindingTicketStatus
	ExpiresAt        time.Time
	ConsumedAt       *time.Time
	Version          int64
	CreatedAt        time.Time
	UpdatedAt        time.Time
}

func RestoreFederatedPhoneBindingTicket(
	ticket FederatedPhoneBindingTicket,
) (FederatedPhoneBindingTicket, error) {
	ticket.ID = strings.TrimSpace(ticket.ID)
	ticket.Hash = strings.TrimSpace(ticket.Hash)
	ticket.CredentialKey = strings.TrimSpace(ticket.CredentialKey)
	ticket.DisplayName = strings.TrimSpace(ticket.DisplayName)
	ticket.AvatarURL = strings.TrimSpace(ticket.AvatarURL)
	ticket.DeviceID = strings.TrimSpace(ticket.DeviceID)
	ticket.Platform = strings.TrimSpace(ticket.Platform)
	ticket.AppVersion = strings.TrimSpace(ticket.AppVersion)
	ticket.AgreementVersion = strings.TrimSpace(ticket.AgreementVersion)
	ticket.PrivacyVersion = strings.TrimSpace(ticket.PrivacyVersion)
	ticket.ExpiresAt = ticket.ExpiresAt.UTC()
	ticket.CreatedAt = ticket.CreatedAt.UTC()
	ticket.UpdatedAt = ticket.UpdatedAt.UTC()
	if ticket.ConsumedAt != nil {
		consumedAt := ticket.ConsumedAt.UTC()
		ticket.ConsumedAt = &consumedAt
	}
	if err := ticket.Validate(); err != nil {
		return FederatedPhoneBindingTicket{}, err
	}
	return ticket, nil
}

func (ticket FederatedPhoneBindingTicket) Validate() error {
	expectedProvider, providerErr := ProviderForCredentialType(ticket.CredentialType)
	if invalidText(ticket.ID, 64) || len(ticket.Hash) != 64 ||
		invalidText(ticket.CredentialKey, 256) ||
		invalidOptionalText(ticket.DisplayName, 64) ||
		invalidOptionalText(ticket.AvatarURL, 4096) ||
		invalidText(ticket.DeviceID, 128) ||
		invalidText(ticket.Platform, 16) ||
		invalidText(ticket.AppVersion, 32) ||
		invalidText(ticket.AgreementVersion, 64) ||
		invalidText(ticket.PrivacyVersion, 64) ||
		!ticket.Provider.Valid() || !ticket.CredentialType.Valid() ||
		providerErr != nil || expectedProvider != ticket.Provider ||
		ticket.Version < 1 || ticket.CreatedAt.IsZero() ||
		ticket.ExpiresAt.IsZero() || ticket.UpdatedAt.IsZero() ||
		!ticket.ExpiresAt.After(ticket.CreatedAt) {
		return ErrInvalidFederatedPhoneBindingTicket
	}
	switch ticket.Status {
	case FederatedPhoneBindingTicketPending:
		if ticket.ConsumedAt != nil {
			return ErrInvalidFederatedPhoneBindingTicket
		}
	case FederatedPhoneBindingTicketConsumed:
		if ticket.ConsumedAt == nil {
			return ErrInvalidFederatedPhoneBindingTicket
		}
	default:
		return ErrInvalidFederatedPhoneBindingTicket
	}
	return nil
}

func (ticket FederatedPhoneBindingTicket) MatchesContext(
	deviceID string,
	platform string,
	appVersion string,
	agreementVersion string,
	privacyVersion string,
) bool {
	return ticket.DeviceID == strings.TrimSpace(deviceID) &&
		ticket.Platform == strings.TrimSpace(platform) &&
		ticket.AppVersion == strings.TrimSpace(appVersion) &&
		ticket.AgreementVersion == strings.TrimSpace(agreementVersion) &&
		ticket.PrivacyVersion == strings.TrimSpace(privacyVersion)
}

func ProviderForCredentialType(
	credentialType CredentialType,
) (FederatedProvider, error) {
	switch credentialType {
	case CredentialTypeFederatedSlotA:
		return FederatedProviderSlotA, nil
	case CredentialTypeFederatedSlotB:
		return FederatedProviderSlotB, nil
	case CredentialTypeFederatedSlotC:
		return FederatedProviderSlotC, nil
	default:
		return "", fmt.Errorf(
			"%w: unsupported federated credential type",
			ErrInvalidFederatedPhoneBindingTicket,
		)
	}
}
