// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/auth-token-lifecycle/spec.md#gwt-002
// readiness_case: refresh-token-local
// readiness_case: logout-local
package local_contract

import (
	"context"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	sessionapp "quwoquan_service/services/user-service/internal/account/account_session/application"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountports "quwoquan_service/services/user-service/internal/account/user_account/domain/ports"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestRefreshAndLogoutUseAccountSessionFacadeAndAuthoritativeAccountState(t *testing.T) {
	store := newFakeAccountSessionStore()
	sessions := sessionapp.NewAccountSessionCommandFacade(store)
	const originalToken = "account-session-original-refresh"
	issued, err := sessions.Issue(context.Background(), sessionapp.IssueCommand{
		AccountID:             "session-owner",
		DeviceID:              "session-device",
		AuthenticationSubject: "session-subject",
		IdentityOrigin:        "phone",
		RefreshToken:          []byte(originalToken),
		ExpiresAt:             time.Now().UTC().Add(24 * time.Hour),
	})
	if err != nil {
		t.Fatalf("seed AccountSession: %v", err)
	}
	profiles := &accountSessionOperationProfileStore{profile: &usermodel.UserProfile{
		UserID:                   "session-owner",
		AccountState:             "active",
		IdentityOrigin:           "phone",
		AnonymousRetentionPolicy: "preserve",
		LogicalShard:             1,
	}}
	personas := &accountSessionOperationPersonaStore{persona: &usermodel.Persona{
		UserID:      "session-owner",
		PersonaID:   "session-persona",
		DisplayName: "Session Owner",
		IsActive:    true,
		Version:     1,
	}}
	signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
		Secret:       []byte("account-session-local-secret-32bytes"),
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
		nil,
		nil,
		nil,
		accountapp.WithAccountSessionCommands(sessions),
		accountapp.WithAccountSecurityReader(accountSessionOperationSecurityReader{}),
		accountapp.WithAccessTokenSigner(signer),
	)

	rotated, err := service.RefreshToken(context.Background(), originalToken)
	if err != nil {
		t.Fatalf("RefreshToken: %v", err)
	}
	if rotated.OwnerID != "session-owner" || rotated.RefreshToken == "" ||
		rotated.RefreshToken == originalToken || rotated.AccessToken == "" ||
		rotated.ActivePersona == nil || rotated.ActivePersona["personaId"] != "session-persona" ||
		store.activeCountForLineage(issued.LineageID) != 1 {
		t.Fatalf("rotated session did not preserve authoritative identity: %+v", rotated)
	}

	if err := service.Logout(context.Background(), "session-owner", rotated.RefreshToken); err != nil {
		t.Fatalf("Logout: %v", err)
	}
	if got := store.activeCountForLineage(issued.LineageID); got != 0 {
		t.Fatalf("Logout left %d active AccountSession records", got)
	}
	if _, err := service.RefreshToken(context.Background(), rotated.RefreshToken); err == nil {
		t.Fatal("logged-out refresh token was accepted")
	}
}

type accountSessionOperationProfileStore struct {
	profile *usermodel.UserProfile
}

func (store *accountSessionOperationProfileStore) FindByID(
	context.Context,
	string,
) (*usermodel.UserProfile, error) {
	return store.profile, nil
}

func (*accountSessionOperationProfileStore) FindByNickname(context.Context, string) (*usermodel.UserProfile, error) {
	return nil, nil
}

func (*accountSessionOperationProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	return nil, nil
}

func (*accountSessionOperationProfileStore) CreateAccount(context.Context, userports.UserAccountCreate) error {
	return nil
}

func (*accountSessionOperationProfileStore) PromoteRegistration(context.Context, userports.RegistrationPromotion) error {
	return nil
}

type accountSessionOperationPersonaStore struct {
	persona *usermodel.Persona
}

func (store *accountSessionOperationPersonaStore) FindByID(context.Context, string) (*usermodel.Persona, error) {
	return store.persona, nil
}

func (store *accountSessionOperationPersonaStore) FindByUserID(context.Context, string) ([]usermodel.Persona, error) {
	return []usermodel.Persona{*store.persona}, nil
}

func (store *accountSessionOperationPersonaStore) FindActiveByUserID(context.Context, string) (*usermodel.Persona, error) {
	return store.persona, nil
}

func (store *accountSessionOperationPersonaStore) FindByUserHandle(context.Context, string) (*usermodel.Persona, error) {
	return store.persona, nil
}

func (store *accountSessionOperationPersonaStore) FindByPersonaID(context.Context, string) (*usermodel.Persona, error) {
	return store.persona, nil
}

type accountSessionOperationSecurityReader struct{}

func (accountSessionOperationSecurityReader) ReadAccountSecurity(
	context.Context,
	string,
) (accountports.AccountSecuritySnapshot, error) {
	return accountports.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    1,
	}, nil
}

var (
	_ userports.UserProfileStore         = (*accountSessionOperationProfileStore)(nil)
	_ accountapp.PersonaStore            = (*accountSessionOperationPersonaStore)(nil)
	_ accountports.AccountSecurityReader = accountSessionOperationSecurityReader{}
)
