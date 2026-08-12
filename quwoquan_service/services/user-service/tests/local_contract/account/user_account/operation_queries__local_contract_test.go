// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-profile-subject-and-visibility/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/social-graph-read/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/user-service-cloud-delivery/remote-profile-delivery/spec.md#gwt-001
// readiness_case: list-personas-local
// readiness_case: get-persona-management-summary-local
// readiness_case: get-active-persona-context-local
// readiness_case: get-persona-lifecycle-guard-local
// readiness_case: get-persona-profile-local
// readiness_case: get-user-homepage-bundle-local
// readiness_case: get-me-profile-local
// readiness_case: search-social-relations-local
// readiness_case: pull-user-sync-local
// readiness_case: get-user-profile-local
// readiness_case: get-profile-edit-snapshot-local
// readiness_case: get-profile-qr-card-local
// readiness_case: resolve-profile-qr-token-local
package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"

	rerrors "quwoquan_service/runtime/errors"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	credentialports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	userhttp "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
)

func TestUserAccountPersonaQueryOperationsCallTheOwningFacade(t *testing.T) {
	profileStore := &readinessProfileStore{profile: readinessProfile()}
	personaStore := &readinessPersonaStore{personas: []usermodel.Persona{readinessPersona()}}
	service := application.NewPersonaService(
		personaStore,
		&readinessPersonaCommands{},
		&readinessPersonaProjector{},
		profileStore,
		readinessProfileCache{},
	)

	personas, err := service.ListPersonas(t.Context(), "owner-readiness")
	if err != nil || len(personas) != 1 || personas[0].PersonaID != "persona-readiness" {
		t.Fatalf("ListPersonas()=%+v err=%v", personas, err)
	}
	summary, err := service.GetPersonaManagementSummary(t.Context(), "owner-readiness")
	if err != nil || summary["activeContext"] == nil || summary["quota"] == nil {
		t.Fatalf("GetPersonaManagementSummary()=%+v err=%v", summary, err)
	}
	active, err := service.GetActivePersonaContextView(t.Context(), "owner-readiness")
	if err != nil || active["personaId"] != "persona-readiness" {
		t.Fatalf("GetActivePersonaContextView()=%+v err=%v", active, err)
	}
	if avatarVersion, ok := active["avatarVersion"].(int); !ok || avatarVersion != 0 {
		t.Fatalf(
			"GetActivePersonaContextView() avatarVersion=%#v, want canonical int(0)",
			active["avatarVersion"],
		)
	}
	guard, err := service.GetPersonaLifecycleGuard(
		t.Context(), "owner-readiness", "persona-readiness",
	)
	if err != nil || guard["personaId"] != "persona-readiness" {
		t.Fatalf("GetPersonaLifecycleGuard()=%+v err=%v", guard, err)
	}
	public, err := service.GetPersonaProfileView(t.Context(), "persona-readiness")
	if err != nil || public["personaId"] != "persona-readiness" {
		t.Fatalf("GetPersonaProfileView()=%+v err=%v", public, err)
	}
	me, err := service.GetMeProfileView(t.Context(), "owner-readiness")
	if err != nil || me["personaId"] != "persona-readiness" {
		t.Fatalf("GetMeProfileView()=%+v err=%v", me, err)
	}

	credentials := credentialapp.NewCredentialQueryFacade(&readinessCredentialStore{})
	relationship := relationshipapp.NewPersonaRelationshipService(
		&fakeRelationshipStore{},
		&fakePersonaReader{personas: map[string]*usermodel.Persona{
			"persona-readiness": ptrReadinessPersona(),
		}},
		nil,
		nil,
	)
	handler, err := userhttp.NewUserHandler(
		nil, nil, relationship, nil, nil, credentials, service, nil,
	)
	if err != nil {
		t.Fatalf("NewUserHandler(): %v", err)
	}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(
		http.MethodGet,
		"/user/personas/persona-readiness/homepage-bundle",
		nil,
	)
	handler.Routes().ServeHTTP(recorder, request)
	if recorder.Code != http.StatusOK ||
		!strings.Contains(recorder.Body.String(), `"personaId":"persona-readiness"`) ||
		!strings.Contains(recorder.Body.String(), `"isGuest":true`) {
		t.Fatalf("GetUserHomepageBundle status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func TestGetActivePersonaContextFailsClosedWhenCanonicalSubjectIsUnavailable(t *testing.T) {
	tests := []struct {
		name         string
		profileStore *readinessProfileStore
		personaStore *readinessPersonaStore
	}{
		{
			name:         "owner profile missing",
			profileStore: &readinessProfileStore{},
			personaStore: &readinessPersonaStore{personas: []usermodel.Persona{readinessPersona()}},
		},
		{
			name:         "active persona missing",
			profileStore: &readinessProfileStore{profile: readinessProfile()},
			personaStore: &readinessPersonaStore{},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			service := application.NewPersonaService(
				test.personaStore,
				&readinessPersonaCommands{},
				&readinessPersonaProjector{},
				test.profileStore,
				readinessProfileCache{},
			)

			view, err := service.GetActivePersonaContextView(t.Context(), "owner-readiness")
			if view != nil {
				t.Fatalf("GetActivePersonaContextView() view=%+v, want nil", view)
			}
			appErr := rerrors.NormalizeError(err)
			if appErr.Code.String() != "USER.SYSTEM.internal_error" || appErr.HTTPStatus != http.StatusInternalServerError {
				t.Fatalf("GetActivePersonaContextView() err=%+v", appErr)
			}
		})
	}
}

func TestUserAccountProfileQueryOperationsCallTheOwningFacade(t *testing.T) {
	profileStore := &readinessProfileStore{profile: readinessProfile()}
	personaStore := &readinessPersonaStore{personas: []usermodel.Persona{readinessPersona()}}
	qrStore := &readinessProfileQRStore{}
	syncStream := &readinessSyncStream{}
	service, err := application.NewProfileService(
		profileStore,
		personaStore,
		&readinessPersonaCommands{},
		&readinessPersonaProjector{},
		readinessProfileCache{},
		readinessEventPublisher{},
		syncStream,
		application.WithProfileQrTokenStore(qrStore),
		application.WithProfilePublicBaseURL("https://www.quwoquan.example"),
	)
	if err != nil {
		t.Fatalf("NewProfileService(): %v", err)
	}

	snapshot, err := service.GetProfile(t.Context(), "owner-readiness")
	if err != nil || snapshot == nil || snapshot.Profile.UserID != "owner-readiness" {
		t.Fatalf("GetProfile()=%+v err=%v", snapshot, err)
	}
	edit, err := service.GetEditSnapshot(t.Context(), "owner-readiness", nil)
	if err != nil || edit["personaId"] != "persona-readiness" || edit["qrCard"] == nil {
		t.Fatalf("GetEditSnapshot()=%+v err=%v", edit, err)
	}
	card, err := service.GetQRCard(t.Context(), "owner-readiness")
	if err != nil {
		t.Fatalf("GetQRCard(): %v", err)
	}
	payload, _ := card["qrPayload"].(string)
	parsed, err := url.Parse(payload)
	if err != nil || parsed.Query().Get("qr") == "" {
		t.Fatalf("GetQRCard() payload=%q err=%v", payload, err)
	}
	resolved, err := service.ResolveProfileQRToken(
		t.Context(), "readiness_handle", parsed.Query().Get("qr"),
	)
	if err != nil || resolved["personaId"] != "persona-readiness" {
		t.Fatalf("ResolveProfileQRToken()=%+v err=%v", resolved, err)
	}
	pulled, err := service.PullSync(t.Context(), "owner-readiness", 4, 20)
	if err != nil || pulled.LatestSyncSeq != 5 || syncStream.pullCalls != 1 {
		t.Fatalf("PullSync()=%+v calls=%d err=%v", pulled, syncStream.pullCalls, err)
	}
}

func TestUserAccountSearchSocialRelationsCallsTheOwningFacade(t *testing.T) {
	profileStore := &readinessProfileStore{profile: readinessProfile()}
	personaStore := &readinessPersonaStore{personas: []usermodel.Persona{readinessPersona()}}
	service := application.NewSearchService(profileStore, personaStore)
	items, err := service.SearchSocialRelations(t.Context(), "readiness_handle", 20)
	if err != nil || len(items) != 1 || items[0]["personaId"] != "persona-readiness" {
		t.Fatalf("SearchSocialRelations()=%+v err=%v", items, err)
	}
}

func readinessProfile() *usermodel.UserProfile {
	return &usermodel.UserProfile{
		UserID:           "owner-readiness",
		AccountState:     "active",
		Nickname:         "Readiness Owner",
		OwnerDisplayName: "Readiness Owner",
		ProfileVersion:   7,
	}
}

func readinessPersona() usermodel.Persona {
	return usermodel.Persona{
		UserID:             "owner-readiness",
		PersonaID:          "persona-readiness",
		UserHandle:         "readiness_handle",
		DisplayName:        "Readiness Persona",
		Status:             "active",
		IsolationLevel:     "open",
		IsActive:           true,
		IsPrimary:          true,
		Version:            3,
		NicknameCustomized: true,
		UpdatedAt:          time.Date(2026, 8, 5, 0, 0, 0, 0, time.UTC),
	}
}

func ptrReadinessPersona() *usermodel.Persona {
	value := readinessPersona()
	return &value
}

type readinessProfileStore struct{ profile *usermodel.UserProfile }

func (store *readinessProfileStore) FindByID(_ context.Context, id string) (*usermodel.UserProfile, error) {
	if store.profile != nil && store.profile.UserID == id {
		copy := *store.profile
		return &copy, nil
	}
	return nil, nil
}
func (*readinessProfileStore) FindByNickname(context.Context, string) (*usermodel.UserProfile, error) {
	return nil, nil
}
func (store *readinessProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	if store.profile == nil {
		return nil, nil
	}
	return []usermodel.UserProfile{*store.profile}, nil
}
func (*readinessProfileStore) CreateAccount(context.Context, userports.UserAccountCreate) error {
	return nil
}
func (*readinessProfileStore) PromoteRegistration(context.Context, userports.RegistrationPromotion) error {
	return nil
}

type readinessPersonaStore struct{ personas []usermodel.Persona }

func (store *readinessPersonaStore) FindByID(ctx context.Context, id string) (*usermodel.Persona, error) {
	return store.FindByPersonaID(ctx, id)
}
func (store *readinessPersonaStore) FindByUserID(_ context.Context, userID string) ([]usermodel.Persona, error) {
	result := make([]usermodel.Persona, 0, len(store.personas))
	for _, persona := range store.personas {
		if persona.UserID == userID {
			result = append(result, persona)
		}
	}
	return result, nil
}
func (store *readinessPersonaStore) FindActiveByUserID(_ context.Context, userID string) (*usermodel.Persona, error) {
	for _, persona := range store.personas {
		if persona.UserID == userID && persona.IsActive {
			copy := persona
			return &copy, nil
		}
	}
	return nil, nil
}
func (store *readinessPersonaStore) FindByUserHandle(_ context.Context, handle string) (*usermodel.Persona, error) {
	for _, persona := range store.personas {
		if persona.UserHandle == handle {
			copy := persona
			return &copy, nil
		}
	}
	return nil, nil
}
func (store *readinessPersonaStore) FindByPersonaID(_ context.Context, id string) (*usermodel.Persona, error) {
	for _, persona := range store.personas {
		if persona.PersonaID == id {
			copy := persona
			return &copy, nil
		}
	}
	return nil, nil
}

type readinessPersonaCommands struct{}

func (*readinessPersonaCommands) CommitCreate(context.Context, *usermodel.Persona, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{PersonaID: "persona-readiness", Version: 3}, nil
}
func (*readinessPersonaCommands) CommitMutation(context.Context, *usermodel.Persona, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{PersonaID: "persona-readiness", Version: 3}, nil
}
func (*readinessPersonaCommands) CommitActivation(context.Context, string, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{PersonaID: "persona-readiness", Version: 3}, nil
}

type readinessPersonaProjector struct{}

func (*readinessPersonaProjector) Project(context.Context, string, int64) (*usermodel.UserProfile, error) {
	return readinessProfile(), nil
}
func (*readinessPersonaProjector) ProjectNext(context.Context) (bool, error) { return false, nil }
func (*readinessPersonaProjector) Run(context.Context, time.Duration) error  { return nil }

type readinessProfileCache struct{}

func (readinessProfileCache) Get(context.Context, string) (*usermodel.FullSnapshot, error) {
	return nil, nil
}
func (readinessProfileCache) Set(context.Context, string, *usermodel.FullSnapshot) error {
	return nil
}
func (readinessProfileCache) Del(context.Context, string) error { return nil }

type readinessEventPublisher struct{}

func (readinessEventPublisher) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

type readinessSyncStream struct{ pullCalls int }

func (*readinessSyncStream) AppendUserAvatarPatch(context.Context, string, application.UserAvatarSyncPatchPayload) (application.UserSyncPatch, error) {
	return application.UserSyncPatch{}, nil
}
func (stream *readinessSyncStream) Pull(context.Context, string, int64, int) (application.PullUserSyncSlice, error) {
	stream.pullCalls++
	return application.PullUserSyncSlice{LatestSyncSeq: 5}, nil
}

type readinessProfileQRStore struct{ token *usermodel.ProfileQrToken }

func (store *readinessProfileQRStore) FindByID(_ context.Context, id string) (*usermodel.ProfileQrToken, error) {
	if store.token != nil && store.token.TokenID == id {
		return store.token, nil
	}
	return nil, nil
}
func (store *readinessProfileQRStore) FindActiveByOwnerAndHandle(context.Context, string, string) (*usermodel.ProfileQrToken, error) {
	return store.token, nil
}
func (store *readinessProfileQRStore) FindByTokenHash(_ context.Context, hash string) (*usermodel.ProfileQrToken, error) {
	if store.token != nil && store.token.TokenHash == hash {
		return store.token, nil
	}
	return nil, nil
}
func (store *readinessProfileQRStore) Create(_ context.Context, token *usermodel.ProfileQrToken) error {
	store.token = token
	return nil
}
func (store *readinessProfileQRStore) Update(_ context.Context, token *usermodel.ProfileQrToken) error {
	store.token = token
	return nil
}

type readinessCredentialStore struct{}

func (*readinessCredentialStore) Bind(context.Context, credentialmodel.ChangeSet) (credentialports.BindResult, error) {
	return credentialports.BindResult{}, nil
}
func (*readinessCredentialStore) LoadByOwnerAndType(context.Context, string, credentialmodel.CredentialType) (credentialmodel.CredentialBinding, bool, error) {
	return credentialmodel.CredentialBinding{}, false, nil
}
func (*readinessCredentialStore) FindByTypeAndKey(context.Context, credentialmodel.CredentialType, string) (credentialmodel.CredentialBinding, bool, error) {
	return credentialmodel.CredentialBinding{}, false, nil
}
func (*readinessCredentialStore) MarkUsed(context.Context, string, time.Time) error { return nil }
func (*readinessCredentialStore) ListByOwner(context.Context, string) ([]credentialmodel.CredentialBinding, error) {
	return nil, nil
}
func (*readinessCredentialStore) CommitRevoke(context.Context, int64, credentialmodel.ChangeSet) error {
	return nil
}
