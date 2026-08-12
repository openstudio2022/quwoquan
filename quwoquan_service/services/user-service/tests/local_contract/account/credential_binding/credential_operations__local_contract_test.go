// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: bind-phone-credential-local
// readiness_case: complete-federated-phone-binding-local
// readiness_case: bind-carrier-phone-credential-local
package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestCredentialOperationsUseVerifiedIdentityAndCanonicalObjectFacets(t *testing.T) {
	store := newFakeCredentialBindingStore()
	commands := bindingapp.NewCredentialCommandFacade(store)
	profiles := &credentialOperationProfileStore{profiles: map[string]*usermodel.UserProfile{
		"credential-owner": {
			UserID:       "credential-owner",
			AccountState: "anonymous",
		},
	}}
	challenges := &credentialOperationChallengeFacet{}
	registrations := &credentialOperationDeviceRegistrar{}
	service := accountapp.NewAuthService(
		profiles,
		nil,
		store,
		nil,
		nil,
		accountapp.WithCredentialCommands(commands),
		accountapp.WithAuthenticationChallenges(challenges),
		accountapp.WithCarrierPhoneResolver(credentialOperationCarrierResolver{}),
		accountapp.WithDeviceRegistration(registrations),
	)

	phoneResult, err := service.BindPhoneCredential(
		context.Background(),
		"credential-owner",
		"+8613800000001",
		"654321",
		"",
	)
	if err != nil {
		t.Fatalf("BindPhoneCredential: %v", err)
	}
	if phoneResult.CredentialType != bindingmodel.CredentialTypePhone ||
		!phoneResult.IsActive ||
		challenges.lastVerify.Purpose != "bind_phone" ||
		string(challenges.lastVerify.Credential) != "654321" {
		t.Fatalf(
			"BindPhoneCredential did not traverse challenge + CredentialBinding facets: result=%+v verify=%+v",
			phoneResult,
			challenges.lastVerify,
		)
	}
	if profiles.lastPromotion.UserID != "credential-owner" ||
		profiles.lastPromotion.Phone != "+8613800000001" {
		t.Fatalf("phone binding did not promote the owning profile: %+v", profiles.lastPromotion)
	}

	carrierResult, err := service.BindCarrierPhoneCredential(
		context.Background(),
		"credential-owner",
		"carrier-proof",
		"physical-device-1",
		"ios",
		"",
	)
	if err != nil {
		t.Fatalf("BindCarrierPhoneCredential: %v", err)
	}
	if carrierResult.CredentialType != bindingmodel.CredentialTypeCarrierPhone ||
		!carrierResult.IsActive ||
		registrations.last.AccountID != "credential-owner" ||
		registrations.last.DeviceID != "physical-device-1" {
		t.Fatalf(
			"carrier binding did not traverse resolver + registration + CredentialBinding facets: result=%+v registration=%+v",
			carrierResult,
			registrations.last,
		)
	}
	if got := store.bindingCount(); got != 2 {
		t.Fatalf("canonical CredentialBinding store count=%d, want 2", got)
	}
}

func TestCompleteFederatedPhoneBindingCommitsOneCanonicalPacket(t *testing.T) {
	shards, err := accountapp.LoadDefaultShardDirectory()
	if err != nil {
		t.Fatalf("load shard directory: %v", err)
	}
	now := time.Date(2026, 8, 5, 12, 0, 0, 0, time.UTC)
	ticket, err := bindingmodel.RestoreFederatedPhoneBindingTicket(
		bindingmodel.FederatedPhoneBindingTicket{
			ID:               "federated-ticket-1",
			Hash:             strings.Repeat("a", 64),
			Provider:         bindingmodel.FederatedProviderSlotA,
			CredentialType:   bindingmodel.CredentialTypeFederatedSlotA,
			CredentialKey:    "federated-subject-1",
			DisplayName:      "Federated User",
			DeviceID:         "device-social-1",
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
		t.Fatalf("restore federated ticket: %v", err)
	}
	packetStore := &credentialOperationFederatedStore{ticket: ticket}
	projector := &credentialOperationPersonaProjector{}
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte("credential-binding-local-secret-32b"),
		Issuer:       "https://auth.quwoquan.local",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          30 * time.Minute,
	})
	if err != nil {
		t.Fatalf("access signer: %v", err)
	}
	service := accountapp.NewAuthService(
		nil,
		nil,
		nil,
		nil,
		shards,
		accountapp.WithFederatedPhoneBindingTickets(packetStore),
		accountapp.WithPersonaCommandPipeline(nil, projector),
		accountapp.WithAccessTokenSigner(signer),
	)

	grant, err := service.CompleteFederatedPhoneBinding(
		context.Background(),
		bindingapp.CompleteFederatedPhoneBindingCommand{
			BindingTicket:    "opaque-ticket-proof",
			Phone:            "+8613800000002",
			OTPCode:          "123456",
			ChallengeID:      "otp-challenge-1",
			DeviceID:         ticket.DeviceID,
			Platform:         ticket.Platform,
			AppVersion:       ticket.AppVersion,
			AgreementVersion: ticket.AgreementVersion,
			PrivacyVersion:   ticket.PrivacyVersion,
		},
	)
	if err != nil {
		t.Fatalf("CompleteFederatedPhoneBinding: %v", err)
	}
	packet := packetStore.packet
	if grant == nil || grant.OwnerID == "" || grant.AccessToken == "" || grant.RefreshToken == "" ||
		packet.ExpectedTicket.ID != ticket.ID ||
		packet.ChallengeID != "otp-challenge-1" ||
		packet.PhoneBinding == nil ||
		packet.SocialBinding.Aggregate.State().CredentialType != bindingmodel.CredentialTypeFederatedSlotA ||
		packet.Session.RefreshTokenHash == "" ||
		projector.personaID != packet.ExpectedPersonaID ||
		projector.version != packet.ExpectedPersonaVer {
		t.Fatalf(
			"federated completion did not commit/project the canonical packet: grant=%+v packet=%+v projector=%s/%d",
			grant,
			packet,
			projector.personaID,
			projector.version,
		)
	}
}

type credentialOperationProfileStore struct {
	profiles      map[string]*usermodel.UserProfile
	lastPromotion userports.RegistrationPromotion
}

func (store *credentialOperationProfileStore) FindByID(
	_ context.Context,
	userID string,
) (*usermodel.UserProfile, error) {
	return store.profiles[strings.TrimSpace(userID)], nil
}

func (*credentialOperationProfileStore) FindByNickname(context.Context, string) (*usermodel.UserProfile, error) {
	return nil, nil
}

func (*credentialOperationProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	return nil, nil
}

func (*credentialOperationProfileStore) CreateAccount(context.Context, userports.UserAccountCreate) error {
	return nil
}

func (store *credentialOperationProfileStore) PromoteRegistration(
	_ context.Context,
	command userports.RegistrationPromotion,
) error {
	store.lastPromotion = command
	return nil
}

type credentialOperationChallengeFacet struct {
	lastVerify challengeapp.VerifyChallengeCommand
}

func (*credentialOperationChallengeFacet) CreateChallenge(
	context.Context,
	challengeapp.CreateChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, nil
}

func (facet *credentialOperationChallengeFacet) VerifyChallenge(
	_ context.Context,
	command challengeapp.VerifyChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	facet.lastVerify = command
	return challengeapp.ChallengeCommandResult{}, nil
}

func (*credentialOperationChallengeFacet) CancelChallenge(
	context.Context,
	challengeapp.CancelChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, nil
}

func (*credentialOperationChallengeFacet) ReportDeliveryResult(
	context.Context,
	challengeapp.ReportDeliveryResultCommand,
) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, nil
}

type credentialOperationDeviceRegistrar struct {
	last registrationapp.RegisterCommand
}

func (registrar *credentialOperationDeviceRegistrar) Register(
	_ context.Context,
	command registrationapp.RegisterCommand,
) (registrationapp.RegisterResult, error) {
	registrar.last = command
	return registrationapp.RegisterResult{}, nil
}

type credentialOperationCarrierResolver struct{}

func (credentialOperationCarrierResolver) ResolvePhone(
	_ context.Context,
	carrierToken string,
) (accountapp.VerifiedCarrierPhone, error) {
	if carrierToken != "carrier-proof" {
		return accountapp.VerifiedCarrierPhone{}, bindingapp.ErrFederatedBindingContext
	}
	return accountapp.VerifiedCarrierPhone{
		Phone:        "+8613800000003",
		DisplayLabel: "138****0003",
	}, nil
}

type credentialOperationFederatedStore struct {
	ticket bindingmodel.FederatedPhoneBindingTicket
	packet bindingapp.CompleteFederatedPhoneBindingPacket
}

func (*credentialOperationFederatedStore) IssueFederatedPhoneBindingTicket(
	context.Context,
	bindingapp.IssueFederatedPhoneBindingTicket,
) (bindingapp.IssuedFederatedPhoneBindingTicket, error) {
	return bindingapp.IssuedFederatedPhoneBindingTicket{}, nil
}

func (store *credentialOperationFederatedStore) ResolveFederatedPhoneBindingTicket(
	_ context.Context,
	_ string,
) (bindingmodel.FederatedPhoneBindingTicket, error) {
	return store.ticket, nil
}

func (store *credentialOperationFederatedStore) CommitFederatedPhoneBinding(
	_ context.Context,
	packet bindingapp.CompleteFederatedPhoneBindingPacket,
) (bindingapp.FederatedPhoneBindingCompletion, error) {
	store.packet = packet
	return bindingapp.FederatedPhoneBindingCompletion{
		OwnerID:        packet.ExpectedOwnerID,
		PersonaID:      packet.ExpectedPersonaID,
		PersonaVersion: packet.ExpectedPersonaVer,
	}, nil
}

type credentialOperationPersonaProjector struct {
	personaID string
	version   int64
}

func (projector *credentialOperationPersonaProjector) Project(
	_ context.Context,
	personaID string,
	version int64,
) (*usermodel.UserProfile, error) {
	projector.personaID = personaID
	projector.version = version
	return &usermodel.UserProfile{UserID: "projected-owner"}, nil
}

func (*credentialOperationPersonaProjector) ProjectNext(context.Context) (bool, error) {
	return false, nil
}

func (*credentialOperationPersonaProjector) Run(context.Context, time.Duration) error {
	return nil
}

var (
	_ userports.UserProfileStore            = (*credentialOperationProfileStore)(nil)
	_ challengeapp.CommandFacet             = (*credentialOperationChallengeFacet)(nil)
	_ registrationapp.InternalRegisterer    = (*credentialOperationDeviceRegistrar)(nil)
	_ accountapp.CarrierPhoneResolver       = credentialOperationCarrierResolver{}
	_ bindingapp.FederatedPhoneBindingStore = (*credentialOperationFederatedStore)(nil)
	_ userports.PersonaProfileProjector     = (*credentialOperationPersonaProjector)(nil)
)
