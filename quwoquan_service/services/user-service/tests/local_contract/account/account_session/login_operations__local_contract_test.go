// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: login-with-phone-local
// readiness_case: login-with-wechat-local
// readiness_case: login-with-alipay-local
// readiness_case: login-with-qq-local
// readiness_case: login-one-tap-local
// readiness_case: login-anonymous-local
package local_contract

import (
	"context"
	"fmt"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestPublishedLoginOperationsUseBoundAuthServiceFacets(t *testing.T) {
	credentials := newAccountSessionLoginCredentialStore(t)
	profile := &usermodel.UserProfile{
		UserID:                   "login-owner",
		AccountState:             "active",
		IdentityOrigin:           "phone",
		AnonymousRetentionPolicy: "preserve",
		Phone:                    "+8613800000401",
		LogicalShard:             1,
		OwnerDisplayName:         "Login Owner",
	}
	profiles := &accountSessionOperationProfileStore{profile: profile}
	personas := &accountSessionOperationPersonaStore{persona: &usermodel.Persona{
		UserID:      profile.UserID,
		PersonaID:   "login-persona",
		DisplayName: "Login Owner",
		IsActive:    true,
		Version:     1,
	}}
	sessionStore := newFakeAccountSessionStore()
	registrations := &accountSessionLoginDeviceRegistrar{}
	consents := &accountSessionLoginConsentStore{}
	challenges := &accountSessionLoginChallengeFacet{}
	anonymousDevices := &accountSessionLoginAnonymousStore{}
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte("account-session-login-local-32bytes"),
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
		profiles,
		personas,
		credentials,
		anonymousDevices,
		nil,
		accountapp.WithAccountSessionCommands(
			newAccountSessionCommandFacadeForTest(sessionStore),
		),
		accountapp.WithDeviceRegistration(registrations),
		accountapp.WithConsentRecordStore(consents),
		accountapp.WithAuthenticationChallenges(challenges),
		accountapp.WithCarrierPhoneResolver(accountSessionLoginCarrierResolver{}),
		accountapp.WithAccountSecurityReader(accountSessionOperationSecurityReader{}),
		accountapp.WithAccessTokenSigner(signer),
	)

	phone, err := service.LoginWithPhone(
		context.Background(),
		"+8613800000401",
		"246810",
		"138****0401",
		"login-device-phone",
		"ios",
		"1.0.0",
		"agreement-v1",
		"privacy-v1",
	)
	assertAccountSessionLoginGrant(t, "LoginWithPhone", phone, err)
	if challenges.lastVerify.Purpose != "phone_login" ||
		string(challenges.lastVerify.Credential) != "246810" {
		t.Fatalf("phone login did not verify AuthenticationChallenge: %+v", challenges.lastVerify)
	}

	for _, login := range []struct {
		name           string
		credentialType bindingmodel.CredentialType
		credentialKey  string
	}{
		{name: "LoginWithWechat", credentialType: bindingmodel.CredentialTypeFederatedSlotA, credentialKey: "wechat-subject"},
		{name: "LoginWithAlipay", credentialType: bindingmodel.CredentialTypeFederatedSlotB, credentialKey: "alipay-subject"},
		{name: "LoginWithQq", credentialType: bindingmodel.CredentialTypeFederatedSlotC, credentialKey: "qq-subject"},
	} {
		facade := accountapp.NewFederatedLoginFacade(
			service,
			accountSessionLoginIdentityVerifier{
				credentialType: login.credentialType,
				credentialKey:  login.credentialKey,
			},
			nil,
		)
		outcome, err := facade.Login(
			context.Background(),
			"opaque-authorization-code",
			"login-device-"+login.name,
			"ios",
			"1.0.0",
			"agreement-v1",
			"privacy-v1",
		)
		if err != nil || outcome == nil || outcome.Session == nil {
			t.Fatalf("%s outcome=%+v err=%v", login.name, outcome, err)
		}
		assertAccountSessionLoginGrant(t, login.name, outcome.Session, nil)
	}

	oneTap, err := service.LoginWithOneTap(
		context.Background(),
		"carrier-login-proof",
		"login-device-carrier",
		"android",
		"1.0.0",
		"agreement-v1",
		"privacy-v1",
	)
	assertAccountSessionLoginGrant(t, "LoginOneTap", oneTap, err)

	anonymous, err := service.LoginAnonymously(
		context.Background(),
		"install-login-anonymous",
		"fp-account-session",
		"android",
		"1.0.0",
	)
	assertAccountSessionLoginGrant(t, "LoginAnonymous", anonymous, err)

	if got := len(sessionStore.records); got != 6 {
		t.Fatalf("published login operations issued %d AccountSessions, want 6", got)
	}
	if registrations.calls != 5 || len(consents.records) != 5 {
		t.Fatalf("login device/consent calls registration=%d consent=%d want=5/5", registrations.calls, len(consents.records))
	}
	if anonymousDevices.created == nil || anonymousDevices.created.OwnerID != profile.UserID {
		t.Fatalf("anonymous login did not persist device binding: %+v", anonymousDevices.created)
	}
	if credentials.markUsedCalls != 6 {
		t.Fatalf("verified login credentials marked used=%d want=6", credentials.markUsedCalls)
	}
}

func newAccountSessionCommandFacadeForTest(store *fakeAccountSessionStore) *sessionapp.AccountSessionCommandFacade {
	return sessionapp.NewAccountSessionCommandFacade(store)
}

func assertAccountSessionLoginGrant(
	t *testing.T,
	operation string,
	grant *sessionapp.AuthSessionGrant,
	err error,
) {
	t.Helper()
	if err != nil || grant == nil || grant.OwnerID != "login-owner" ||
		grant.AccessToken == "" || grant.RefreshToken == "" ||
		grant.ActivePersona["personaId"] != "login-persona" {
		t.Fatalf("%s grant=%+v err=%v", operation, grant, err)
	}
}

type accountSessionLoginCredentialStore struct {
	byKey         map[string]bindingmodel.CredentialBinding
	markUsedCalls int
}

func newAccountSessionLoginCredentialStore(t *testing.T) *accountSessionLoginCredentialStore {
	t.Helper()
	store := &accountSessionLoginCredentialStore{byKey: map[string]bindingmodel.CredentialBinding{}}
	for index, seed := range []struct {
		credentialType bindingmodel.CredentialType
		credentialKey  string
	}{
		{bindingmodel.CredentialTypePhone, "+8613800000401"},
		{bindingmodel.CredentialTypeFederatedSlotA, "wechat-subject"},
		{bindingmodel.CredentialTypeFederatedSlotB, "alipay-subject"},
		{bindingmodel.CredentialTypeFederatedSlotC, "qq-subject"},
		{bindingmodel.CredentialTypeCarrierPhone, "+8613800000402"},
		{bindingmodel.CredentialTypeAnonymousDevice, "fp-account-session"},
	} {
		change, err := bindingmodel.Bind(bindingmodel.BindParams{
			ID:             fmt.Sprintf("login-binding-%d", index+1),
			OwnerID:        "login-owner",
			CredentialType: seed.credentialType,
			CredentialKey:  seed.credentialKey,
			DisplayLabel:   string(seed.credentialType),
			EventID:        fmt.Sprintf("login-event-%d", index+1),
			BoundAt:        time.Date(2026, 8, 5, 12, index, 0, 0, time.UTC),
		})
		if err != nil {
			t.Fatalf("seed %s login credential: %v", seed.credentialType, err)
		}
		store.byKey[accountSessionLoginCredentialKey(seed.credentialType, seed.credentialKey)] = change.Aggregate
	}
	return store
}

func (store *accountSessionLoginCredentialStore) Bind(
	_ context.Context,
	change bindingmodel.ChangeSet,
) (bindingports.BindResult, error) {
	state := change.Aggregate.State()
	store.byKey[accountSessionLoginCredentialKey(state.CredentialType, state.CredentialKey)] = change.Aggregate
	return bindingports.BindResult{Aggregate: change.Aggregate}, nil
}

func (*accountSessionLoginCredentialStore) LoadByOwnerAndType(context.Context, string, bindingmodel.CredentialType) (bindingmodel.CredentialBinding, bool, error) {
	return bindingmodel.CredentialBinding{}, false, nil
}

func (store *accountSessionLoginCredentialStore) FindByTypeAndKey(
	_ context.Context,
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) (bindingmodel.CredentialBinding, bool, error) {
	binding, found := store.byKey[accountSessionLoginCredentialKey(credentialType, credentialKey)]
	return binding, found, nil
}

func (store *accountSessionLoginCredentialStore) MarkUsed(context.Context, string, time.Time) error {
	store.markUsedCalls++
	return nil
}

func (store *accountSessionLoginCredentialStore) ListByOwner(context.Context, string) ([]bindingmodel.CredentialBinding, error) {
	result := make([]bindingmodel.CredentialBinding, 0, len(store.byKey))
	for _, binding := range store.byKey {
		result = append(result, binding)
	}
	return result, nil
}

func (*accountSessionLoginCredentialStore) CommitRevoke(context.Context, int64, bindingmodel.ChangeSet) error {
	return nil
}

func accountSessionLoginCredentialKey(
	credentialType bindingmodel.CredentialType,
	credentialKey string,
) string {
	return string(credentialType) + "\x00" + credentialKey
}

type accountSessionLoginChallengeFacet struct {
	lastVerify challengeapp.VerifyChallengeCommand
}

func (*accountSessionLoginChallengeFacet) CreateChallenge(context.Context, challengeapp.CreateChallengeCommand) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, nil
}

func (facet *accountSessionLoginChallengeFacet) VerifyChallenge(
	_ context.Context,
	command challengeapp.VerifyChallengeCommand,
) (challengeapp.ChallengeCommandResult, error) {
	facet.lastVerify = command
	return challengeapp.ChallengeCommandResult{}, nil
}

func (*accountSessionLoginChallengeFacet) CancelChallenge(context.Context, challengeapp.CancelChallengeCommand) (challengeapp.ChallengeCommandResult, error) {
	return challengeapp.ChallengeCommandResult{}, nil
}

type accountSessionLoginDeviceRegistrar struct {
	calls int
}

func (registrar *accountSessionLoginDeviceRegistrar) Register(
	context.Context,
	registrationapp.RegisterCommand,
) (registrationapp.RegisterResult, error) {
	registrar.calls++
	return registrationapp.RegisterResult{}, nil
}

type accountSessionLoginConsentStore struct {
	records []userports.ConsentRecord
}

func (store *accountSessionLoginConsentStore) Create(
	_ context.Context,
	record *userports.ConsentRecord,
) error {
	store.records = append(store.records, *record)
	return nil
}

type accountSessionLoginAnonymousStore struct {
	created *usermodel.AnonymousDeviceBinding
}

func (store *accountSessionLoginAnonymousStore) FindByDeviceFingerprintHash(context.Context, string) (*usermodel.AnonymousDeviceBinding, error) {
	return store.created, nil
}

func (store *accountSessionLoginAnonymousStore) Create(
	_ context.Context,
	binding *usermodel.AnonymousDeviceBinding,
) error {
	store.created = binding
	return nil
}

func (*accountSessionLoginAnonymousStore) Touch(context.Context, string, string, string, string) error {
	return nil
}

type accountSessionLoginIdentityVerifier struct {
	credentialType bindingmodel.CredentialType
	credentialKey  string
}

func (verifier accountSessionLoginIdentityVerifier) Verify(
	context.Context,
	string,
) (accountapp.VerifiedFederatedIdentity, error) {
	return accountapp.VerifiedFederatedIdentity{
		CredentialType: verifier.credentialType,
		CredentialKey:  verifier.credentialKey,
		DisplayName:    "Federated Login Owner",
	}, nil
}

type accountSessionLoginCarrierResolver struct{}

func (accountSessionLoginCarrierResolver) ResolvePhone(
	context.Context,
	string,
) (accountapp.VerifiedCarrierPhone, error) {
	return accountapp.VerifiedCarrierPhone{
		Phone:        "+8613800000402",
		DisplayLabel: "138****0402",
	}, nil
}

var (
	_ bindingports.AggregateStore           = (*accountSessionLoginCredentialStore)(nil)
	_ challengeapp.CommandFacet             = (*accountSessionLoginChallengeFacet)(nil)
	_ registrationapp.InternalRegisterer    = (*accountSessionLoginDeviceRegistrar)(nil)
	_ userports.ConsentRecordStore          = (*accountSessionLoginConsentStore)(nil)
	_ userports.AnonymousDeviceBindingStore = (*accountSessionLoginAnonymousStore)(nil)
	_ accountapp.FederatedIdentityVerifier  = accountSessionLoginIdentityVerifier{}
	_ accountapp.CarrierPhoneResolver       = accountSessionLoginCarrierResolver{}
)
