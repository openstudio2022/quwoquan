package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

func assertProfileErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

type profileErrCodeProfiles struct {
	profiles map[string]*usermodel.UserProfile
}

func (store profileErrCodeProfiles) FindByID(
	_ context.Context,
	id string,
) (*usermodel.UserProfile, error) {
	return store.profiles[id], nil
}

func (store profileErrCodeProfiles) FindByNickname(
	context.Context,
	string,
) (*usermodel.UserProfile, error) {
	return nil, nil
}

func (profileErrCodeProfiles) SearchProfiles(
	context.Context,
	string,
	int,
) ([]usermodel.UserProfile, error) {
	return nil, nil
}

func (profileErrCodeProfiles) CreateAccount(
	context.Context,
	userports.UserAccountCreate,
) error {
	return nil
}

func (profileErrCodeProfiles) PromoteRegistration(
	context.Context,
	userports.RegistrationPromotion,
) error {
	return nil
}

type profileErrCodePersonas struct {
	personas map[string]*usermodel.Persona
}

func (store profileErrCodePersonas) FindByID(
	_ context.Context,
	id string,
) (*usermodel.Persona, error) {
	return store.personas[id], nil
}

func (store profileErrCodePersonas) FindByPersonaID(
	_ context.Context,
	id string,
) (*usermodel.Persona, error) {
	return store.personas[id], nil
}

func (store profileErrCodePersonas) FindByUserHandle(
	context.Context,
	string,
) (*usermodel.Persona, error) {
	return nil, nil
}

func (store profileErrCodePersonas) FindByUserID(
	_ context.Context,
	ownerID string,
) ([]usermodel.Persona, error) {
	result := make([]usermodel.Persona, 0, len(store.personas))
	for _, persona := range store.personas {
		if persona.UserID == ownerID {
			result = append(result, *persona)
		}
	}
	return result, nil
}

func (store profileErrCodePersonas) FindActiveByUserID(
	_ context.Context,
	ownerID string,
) (*usermodel.Persona, error) {
	for _, persona := range store.personas {
		if persona.UserID == ownerID && persona.IsActive {
			return persona, nil
		}
	}
	return nil, nil
}

// profileErrCodeConflictCommands 让每次聚合提交都返回版本冲突。
type profileErrCodeConflictCommands struct{}

func (profileErrCodeConflictCommands) CommitCreate(
	context.Context,
	*usermodel.Persona,
	personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
}

func (profileErrCodeConflictCommands) CommitMutation(
	context.Context,
	*usermodel.Persona,
	string,
	personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
}

func (profileErrCodeConflictCommands) CommitActivation(
	context.Context,
	string,
	string,
	personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, personaports.ErrPersonaVersionConflict
}

type profileErrCodeProjector struct{}

func (profileErrCodeProjector) Project(
	context.Context,
	string,
	int64,
) (*usermodel.UserProfile, error) {
	return &usermodel.UserProfile{}, nil
}

func (profileErrCodeProjector) ProjectNext(context.Context) (bool, error) {
	return false, nil
}

func (profileErrCodeProjector) Run(context.Context, time.Duration) error {
	return nil
}

type profileErrCodeCache struct{}

func (profileErrCodeCache) Get(
	context.Context,
	string,
) (*usermodel.FullSnapshot, error) {
	return nil, nil
}

func (profileErrCodeCache) Set(
	context.Context,
	string,
	*usermodel.FullSnapshot,
) error {
	return nil
}

func (profileErrCodeCache) Del(context.Context, string) error { return nil }

type profileErrCodeEvents struct{}

func (profileErrCodeEvents) PublishUserEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}

type profileErrCodeQrTokens struct {
	byHash map[string]*usermodel.ProfileQrToken
}

func (store profileErrCodeQrTokens) FindByID(
	context.Context,
	string,
) (*usermodel.ProfileQrToken, error) {
	return nil, nil
}

func (store profileErrCodeQrTokens) FindActiveByOwnerAndHandle(
	context.Context,
	string,
	string,
) (*usermodel.ProfileQrToken, error) {
	return nil, nil
}

func (store profileErrCodeQrTokens) FindByTokenHash(
	_ context.Context,
	tokenHash string,
) (*usermodel.ProfileQrToken, error) {
	return store.byHash[tokenHash], nil
}

func (profileErrCodeQrTokens) Create(
	context.Context,
	*usermodel.ProfileQrToken,
) error {
	return nil
}

func (profileErrCodeQrTokens) Update(
	context.Context,
	*usermodel.ProfileQrToken,
) error {
	return nil
}

type profileErrCodeQrTokensAnyHash struct {
	profileErrCodeQrTokens
	token *usermodel.ProfileQrToken
}

func (store profileErrCodeQrTokensAnyHash) FindByTokenHash(
	context.Context,
	string,
) (*usermodel.ProfileQrToken, error) {
	return store.token, nil
}

func newProfileErrCodeService(
	t *testing.T,
	profiles profileErrCodeProfiles,
	personas profileErrCodePersonas,
	options ...application.ProfileServiceOption,
) *application.ProfileService {
	t.Helper()
	service, err := application.NewProfileService(
		profiles,
		personas,
		profileErrCodeConflictCommands{},
		profileErrCodeProjector{},
		profileErrCodeCache{},
		profileErrCodeEvents{},
		nil,
		options...,
	)
	if err != nil {
		t.Fatalf("construct ProfileService: %v", err)
	}
	return service
}

func profileErrCodeMeta(key string) application.PersonaCommandMeta {
	return application.PersonaCommandMeta{
		IdempotencyKey: key,
		CommandDigest:  "sha256:cc4c9a72efb00ef0376136712bc233e71e6a4f7692a302526c780fc41e7771f8",
	}
}

func profileErrCodeFixture() (profileErrCodeProfiles, profileErrCodePersonas) {
	profiles := profileErrCodeProfiles{
		profiles: map[string]*usermodel.UserProfile{
			"owner-1": {
				UserID:       "owner-1",
				Nickname:     "Owner",
				AccountState: "active",
				UpdatedAt:    time.Now().UTC(),
			},
		},
	}
	personas := profileErrCodePersonas{
		personas: map[string]*usermodel.Persona{
			"persona-1": {
				UserID:      "owner-1",
				PersonaID:   "persona-1",
				DisplayName: "Owner Persona",
				IsPrimary:   true,
				IsActive:    true,
				Status:      "active",
				Version:     1,
			},
		},
	}
	return profiles, personas
}

func TestUpdateProfileSurfacesUserNotFoundForUnknownAccount(t *testing.T) {
	t.Parallel()
	profiles, personas := profileErrCodeFixture()
	service := newProfileErrCodeService(t, profiles, personas)

	nickname := "Ghost"
	_, err := service.UpdateProfile(
		context.Background(),
		"missing-owner",
		application.ProfileUpdateCommand{Nickname: &nickname},
		profileErrCodeMeta("update-missing-owner"),
	)
	assertProfileErrorCode(t, err, "USER.USER.not_found")
}

func TestUpdateProfileRejectsInvalidIdentityTagRoot(t *testing.T) {
	t.Parallel()
	profiles, personas := profileErrCodeFixture()
	service := newProfileErrCodeService(t, profiles, personas)

	_, err := service.UpdateProfile(
		context.Background(),
		"owner-1",
		application.ProfileUpdateCommand{
			IdentityTags: []string{"Forbidden/根分类/子标签"},
		},
		profileErrCodeMeta("update-invalid-tag"),
	)
	assertProfileErrorCode(t, err, "USER.PROFILE.invalid_tag_ref")
}

func TestUpdateProfileSurfacesVersionConflictFromCommandStore(t *testing.T) {
	t.Parallel()
	profiles, personas := profileErrCodeFixture()
	service := newProfileErrCodeService(t, profiles, personas)

	nickname := "Renamed Owner"
	_, err := service.UpdateProfile(
		context.Background(),
		"owner-1",
		application.ProfileUpdateCommand{Nickname: &nickname},
		profileErrCodeMeta("update-version-conflict"),
	)
	assertProfileErrorCode(t, err, "USER.PROFILE.version_conflict")
}

func TestResolveProfileQRTokenSurfacesExpiredToken(t *testing.T) {
	t.Parallel()
	profiles, personas := profileErrCodeFixture()
	expiredAt := time.Now().UTC().Add(-time.Hour)
	service := newProfileErrCodeService(
		t,
		profiles,
		personas,
		application.WithProfileQrTokenStore(profileErrCodeQrTokensAnyHash{
			token: &usermodel.ProfileQrToken{
				TokenID:     "token-1",
				TokenHash:   "any",
				OwnerUserID: "owner-1",
				PersonaID:   "persona-1",
				UserHandle:  "qwowner",
				Status:      "active",
				ExpiresAt:   &expiredAt,
			},
		}),
	)

	_, err := service.ResolveProfileQRToken(
		context.Background(),
		"qwowner",
		"raw-token-value",
	)
	assertProfileErrorCode(t, err, "USER.PROFILE.qr_token_expired")
}
