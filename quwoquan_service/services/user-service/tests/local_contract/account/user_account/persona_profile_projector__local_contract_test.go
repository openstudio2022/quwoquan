// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// readiness_case: materialize-active-persona-profile-local
package local_contract

import (
	"context"
	"testing"
	"time"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

func TestActivatePersonaExecutesCanonicalProfileProjector(t *testing.T) {
	personas := personaProjectionStore{values: []usermodel.Persona{{
		UserID: "owner-1", PersonaID: "persona-2", DisplayName: "旅人", Status: "active",
	}}}
	commands := &personaProjectionCommands{}
	projectionPort := &personaProjectionRunner{}
	projector, err := application.NewPersonaProfileProjector(projectionPort)
	if err != nil {
		t.Fatalf("NewPersonaProfileProjector(): %v", err)
	}
	service := application.NewPersonaService(
		personas, commands, projector, nil, personaProjectionCache{},
	)
	err = service.ActivatePersona(t.Context(), "owner-1", "persona-2", application.PersonaCommandMeta{
		IdempotencyKey: "activate-persona-2", CommandDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
	})
	if err != nil {
		t.Fatalf("ActivatePersona(): %v", err)
	}
	if commands.activations != 1 || projectionPort.calls != 1 ||
		projectionPort.personaID != "persona-2" || projectionPort.version != 7 {
		t.Fatalf("commands=%d projectionPort=%+v", commands.activations, projectionPort)
	}
}

type personaProjectionStore struct{ values []usermodel.Persona }

func (store personaProjectionStore) FindByID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}
func (store personaProjectionStore) FindByUserID(context.Context, string) ([]usermodel.Persona, error) {
	return append([]usermodel.Persona(nil), store.values...), nil
}
func (store personaProjectionStore) FindActiveByUserID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}
func (store personaProjectionStore) FindByUserHandle(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}
func (store personaProjectionStore) FindByPersonaID(context.Context, string) (*usermodel.Persona, error) {
	return nil, nil
}

type personaProjectionCommands struct{ activations int }

func (*personaProjectionCommands) CommitCreate(
	context.Context, *usermodel.Persona, personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, nil
}
func (*personaProjectionCommands) CommitMutation(
	context.Context, *usermodel.Persona, string, personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	return personaports.PersonaCommandResult{}, nil
}
func (store *personaProjectionCommands) CommitActivation(
	_ context.Context, _ string, personaID string, _ personaports.PersonaCommandMeta,
) (personaports.PersonaCommandResult, error) {
	store.activations++
	return personaports.PersonaCommandResult{PersonaID: personaID, Version: 7}, nil
}

type personaProjectionRunner struct {
	calls     int
	personaID string
	version   int64
}

func (runner *personaProjectionRunner) Project(
	_ context.Context, personaID string, version int64,
) (*usermodel.UserProfile, error) {
	runner.calls++
	runner.personaID = personaID
	runner.version = version
	return &usermodel.UserProfile{UserID: "owner-1"}, nil
}
func (*personaProjectionRunner) ProjectNext(context.Context) (bool, error) { return false, nil }
func (*personaProjectionRunner) Run(context.Context, time.Duration) error  { return nil }

type personaProjectionCache struct{}

func (personaProjectionCache) Del(context.Context, string) error { return nil }
