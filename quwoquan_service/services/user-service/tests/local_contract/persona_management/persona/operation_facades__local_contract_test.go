// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// readiness_case: create-persona-local
// readiness_case: update-persona-local
// readiness_case: apply-persona-profile-sync-local
// readiness_case: retire-persona-local
// readiness_case: activate-persona-local
// readiness_case: update-user-profile-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

type readinessPersonaRuntime struct {
	profiles map[string]*usermodel.UserProfile
	personas map[string]*usermodel.Persona
}

func newReadinessPersonaRuntime(t *testing.T) (*readinessPersonaRuntime, string, string) {
	t.Helper()
	owner, err := useridentity.NewOwnerID("ph", "01j00000000000000000000010")
	if err != nil {
		t.Fatalf("build owner identity: %v", err)
	}
	primary, err := useridentity.NewPersonaID(owner.LogicalShardHex(), "01j00000000000000000000011")
	if err != nil {
		t.Fatalf("build primary persona identity: %v", err)
	}
	ownerID := owner.String()
	primaryID := primary.String()
	runtime := &readinessPersonaRuntime{
		profiles: map[string]*usermodel.UserProfile{
			ownerID: {
				UserID:       ownerID,
				Nickname:     "Primary Persona",
				AccountState: "active",
				UpdatedAt:    time.Now().UTC(),
			},
		},
		personas: map[string]*usermodel.Persona{
			primaryID: {
				UserID:         ownerID,
				PersonaID:      primaryID,
				DisplayName:    "Primary Persona",
				IsPrimary:      true,
				IsActive:       true,
				Status:         "active",
				IsolationLevel: "open",
				Version:        1,
			},
		},
	}
	return runtime, ownerID, primaryID
}

func (runtime *readinessPersonaRuntime) FindByID(_ context.Context, id string) (*usermodel.Persona, error) {
	return runtime.personas[id], nil
}

func (runtime *readinessPersonaRuntime) FindByPersonaID(_ context.Context, id string) (*usermodel.Persona, error) {
	return runtime.personas[id], nil
}

func (runtime *readinessPersonaRuntime) FindByUserHandle(_ context.Context, handle string) (*usermodel.Persona, error) {
	for _, persona := range runtime.personas {
		if persona.UserHandle == handle {
			return persona, nil
		}
	}
	return nil, nil
}

func (runtime *readinessPersonaRuntime) FindByUserID(_ context.Context, ownerID string) ([]usermodel.Persona, error) {
	result := make([]usermodel.Persona, 0, len(runtime.personas))
	for _, persona := range runtime.personas {
		if persona.UserID == ownerID {
			result = append(result, *persona)
		}
	}
	return result, nil
}

func (runtime *readinessPersonaRuntime) FindActiveByUserID(_ context.Context, ownerID string) (*usermodel.Persona, error) {
	for _, persona := range runtime.personas {
		if persona.UserID == ownerID && persona.IsActive && persona.Status != "retired" {
			return persona, nil
		}
	}
	return nil, nil
}

type readinessProfileStore struct {
	runtime *readinessPersonaRuntime
}

func (store readinessProfileStore) FindByID(_ context.Context, id string) (*usermodel.UserProfile, error) {
	return store.runtime.profiles[id], nil
}

func (store readinessProfileStore) FindByNickname(_ context.Context, nickname string) (*usermodel.UserProfile, error) {
	for _, profile := range store.runtime.profiles {
		if profile.Nickname == nickname {
			return profile, nil
		}
	}
	return nil, nil
}

func (readinessProfileStore) SearchProfiles(context.Context, string, int) ([]usermodel.UserProfile, error) {
	return nil, nil
}

func (store readinessProfileStore) CreateAccount(_ context.Context, command userports.UserAccountCreate) error {
	store.runtime.profiles[command.UserID] = &usermodel.UserProfile{UserID: command.UserID, AccountState: command.AccountState}
	return nil
}

func (store readinessProfileStore) PromoteRegistration(_ context.Context, command userports.RegistrationPromotion) error {
	if profile := store.runtime.profiles[command.UserID]; profile != nil {
		profile.AccountState = "active"
		profile.Phone = command.Phone
	}
	return nil
}

type readinessPersonaCommands struct {
	runtime *readinessPersonaRuntime
}

func (commands readinessPersonaCommands) CommitCreate(
	_ context.Context,
	persona *usermodel.Persona,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if meta.IdempotencyKey == "" || meta.CommandDigest == "" {
		return personaports.PersonaCommandResult{}, personaports.ErrPersonaCommandMetaRequired
	}
	ownerPersonaCount := 0
	for _, existing := range commands.runtime.personas {
		if existing.UserID == persona.UserID {
			ownerPersonaCount++
		}
	}
	if ownerPersonaCount >= 5 {
		return personaports.PersonaCommandResult{}, personaports.ErrPersonaQuotaReached
	}
	copy := *persona
	copy.Version = 1
	commands.runtime.personas[persona.PersonaID] = &copy
	return personaports.PersonaCommandResult{PersonaID: persona.PersonaID, Version: 1}, nil
}

func (commands readinessPersonaCommands) CommitMutation(
	_ context.Context,
	persona *usermodel.Persona,
	_ string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if meta.IdempotencyKey == "" || meta.CommandDigest == "" {
		return personaports.PersonaCommandResult{}, personaports.ErrPersonaCommandMetaRequired
	}
	copy := *persona
	copy.Version++
	commands.runtime.personas[persona.PersonaID] = &copy
	return personaports.PersonaCommandResult{PersonaID: persona.PersonaID, Version: int64(copy.Version)}, nil
}

func (commands readinessPersonaCommands) CommitActivation(
	_ context.Context,
	ownerID, personaID string,
	meta personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	if meta.IdempotencyKey == "" || meta.CommandDigest == "" {
		return personaports.PersonaCommandResult{}, personaports.ErrPersonaCommandMetaRequired
	}
	for _, persona := range commands.runtime.personas {
		if persona.UserID == ownerID {
			persona.IsActive = persona.PersonaID == personaID
		}
	}
	target := commands.runtime.personas[personaID]
	target.Version++
	return personaports.PersonaCommandResult{PersonaID: personaID, Version: int64(target.Version)}, nil
}

type readinessPersonaProjector struct {
	runtime *readinessPersonaRuntime
}

func (projector readinessPersonaProjector) Project(_ context.Context, personaID string, _ int64) (*usermodel.UserProfile, error) {
	persona := projector.runtime.personas[personaID]
	profile := projector.runtime.profiles[persona.UserID]
	profile.Nickname = persona.DisplayName
	profile.NicknameCustomized = persona.NicknameCustomized
	profile.ProfileVersion++
	profile.UpdatedAt = time.Now().UTC()
	return profile, nil
}

func (readinessPersonaProjector) ProjectNext(context.Context) (bool, error) { return false, nil }
func (readinessPersonaProjector) Run(context.Context, time.Duration) error  { return nil }

type readinessPersonaCache struct{}

func (readinessPersonaCache) Get(context.Context, string) (*usermodel.FullSnapshot, error) {
	return nil, nil
}
func (readinessPersonaCache) Set(context.Context, string, *usermodel.FullSnapshot) error { return nil }
func (readinessPersonaCache) Del(context.Context, string) error                          { return nil }

type readinessPersonaEvents struct{}

func (readinessPersonaEvents) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func readinessPersonaMeta(key string) application.PersonaCommandMeta {
	return application.PersonaCommandMeta{IdempotencyKey: key, CommandDigest: "sha256:cc4c9a72efb00ef0376136712bc233e71e6a4f7692a302526c780fc41e7771f8"}
}

func TestPersonaOperationsUseTheCanonicalCommandAndProjectionPipeline(t *testing.T) {
	runtime, ownerID, primaryID := newReadinessPersonaRuntime(t)
	profiles := readinessProfileStore{runtime: runtime}
	commands := readinessPersonaCommands{runtime: runtime}
	projector := readinessPersonaProjector{runtime: runtime}
	service := application.NewPersonaService(runtime, commands, projector, profiles, readinessPersonaCache{})

	created, err := service.CreatePersona(t.Context(), ownerID, application.CreatePersonaCommand{
		DisplayName: "Secondary Persona",
	}, readinessPersonaMeta("create-secondary"))
	if err != nil || runtime.personas[created.PersonaID] == nil {
		t.Fatalf("CreatePersona persona=%+v err=%v", created, err)
	}
	updatedName := "Updated Secondary"
	updated, err := service.UpdatePersona(t.Context(), ownerID, created.PersonaID, application.UpdatePersonaCommand{
		DisplayName: &updatedName,
	}, readinessPersonaMeta("update-secondary"))
	if err != nil || updated.DisplayName != updatedName {
		t.Fatalf("UpdatePersona persona=%+v err=%v", updated, err)
	}
	syncResult, err := service.ApplyPersonaProfileSync(t.Context(), ownerID, primaryID, application.PersonaProfileSyncOptions{
		ApplyScope:    "selected_subjects",
		SyncTargetIDs: []string{created.PersonaID},
		FieldsMask:    []string{"displayName"},
	}, readinessPersonaMeta("sync-secondary"))
	if err != nil || syncResult.AppliedCount != 1 || runtime.personas[created.PersonaID].DisplayName != "Primary Persona" {
		t.Fatalf("ApplyPersonaProfileSync result=%+v err=%v", syncResult, err)
	}

	retireCandidate, err := service.CreatePersona(t.Context(), ownerID, application.CreatePersonaCommand{
		DisplayName: "Retire Candidate",
	}, readinessPersonaMeta("create-retire-candidate"))
	if err != nil {
		t.Fatalf("CreatePersona retire candidate: %v", err)
	}
	retired, err := service.RetirePersona(t.Context(), ownerID, retireCandidate.PersonaID, readinessPersonaMeta("retire-candidate"))
	if err != nil || retired["allowed"] != true || runtime.personas[retireCandidate.PersonaID].Status != "retired" {
		t.Fatalf("RetirePersona result=%+v err=%v", retired, err)
	}
	if err := service.ActivatePersona(t.Context(), ownerID, created.PersonaID, readinessPersonaMeta("activate-secondary")); err != nil || !runtime.personas[created.PersonaID].IsActive {
		t.Fatalf("ActivatePersona err=%v state=%+v", err, runtime.personas[created.PersonaID])
	}

	profileService, err := application.NewProfileService(
		profiles, runtime, commands, projector, readinessPersonaCache{}, readinessPersonaEvents{}, nil,
	)
	if err != nil {
		t.Fatalf("construct ProfileService: %v", err)
	}
	profileName := "Profile Operation Name"
	profile, err := profileService.UpdateProfile(t.Context(), ownerID, application.ProfileUpdateCommand{
		DisplayName: &profileName,
	}, readinessPersonaMeta("update-user-profile"))
	if err != nil || profile.Nickname != profileName || runtime.personas[created.PersonaID].DisplayName != profileName {
		t.Fatalf("UpdateUserProfile profile=%+v persona=%+v err=%v", profile, runtime.personas[created.PersonaID], err)
	}
	for index := 0; index < 2; index++ {
		if _, err := service.CreatePersona(t.Context(), ownerID, application.CreatePersonaCommand{
			DisplayName: "Quota Persona",
		}, readinessPersonaMeta("quota-fill-"+string(rune('0'+index)))); err != nil {
			t.Fatalf("fill Persona quota index=%d err=%v", index, err)
		}
	}
	_, err = service.CreatePersona(t.Context(), ownerID, application.CreatePersonaCommand{
		DisplayName: "Over Quota Persona",
	}, readinessPersonaMeta("quota-rejected"))
	assertPersonaQuotaReached(t, err)
}

func assertPersonaQuotaReached(t *testing.T, err error) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != "USER.PERSONA.quota_reached" {
		t.Fatalf("expected USER.PERSONA.quota_reached, got %T: %v", err, err)
	}
}
