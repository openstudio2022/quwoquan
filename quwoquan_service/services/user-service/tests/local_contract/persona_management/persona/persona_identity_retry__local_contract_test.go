// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-004
package local_contract

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	runtimeid "quwoquan_service/runtime/id"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
)

type identityRetryCommands struct {
	failures []error
	seenIDs  []string
}

func (commands *identityRetryCommands) CommitCreate(_ context.Context, persona *usermodel.Persona, _ personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	commands.seenIDs = append(commands.seenIDs, persona.PersonaID)
	index := len(commands.seenIDs) - 1
	if index < len(commands.failures) && commands.failures[index] != nil {
		return personaports.PersonaCommandResult{}, commands.failures[index]
	}
	return personaports.PersonaCommandResult{PersonaID: persona.PersonaID, Version: 1}, nil
}
func (*identityRetryCommands) CommitMutation(context.Context, *usermodel.Persona, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	panic("unused")
}
func (*identityRetryCommands) CommitActivation(context.Context, string, string, personaports.PersonaCommandMeta) (personaports.PersonaCommandResult, error) {
	panic("unused")
}

type identityRetryProjector struct{}

func (identityRetryProjector) Project(_ context.Context, personaID string, _ int64) (*usermodel.UserProfile, error) {
	return &usermodel.UserProfile{UserID: personaID}, nil
}
func (identityRetryProjector) ProjectNext(context.Context) (bool, error) { return false, nil }
func (identityRetryProjector) Run(context.Context, time.Duration) error  { return nil }

type noOpProfileCache struct{}

func (noOpProfileCache) Del(context.Context, string) error { return nil }

func TestCreatePersonaRetriesOnlyIdentityConflictsWithinBudget(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	candidates := []string{
		"us_01_0001_01j00000000000000000000101",
		"us_01_0001_01j00000000000000000000102",
		"us_01_0001_01j00000000000000000000103",
	}
	generated := 0
	commands := &identityRetryCommands{failures: []error{
		personaports.ErrPersonaIdentityConflict,
		personaports.ErrPersonaIdentityConflict,
		nil,
	}}
	service := application.NewPersonaService(
		runtime, commands, identityRetryProjector{}, readinessProfileStore{runtime: runtime}, noOpProfileCache{},
		application.WithPersonaIdentityGenerator(func(string) (string, error) {
			candidate := candidates[generated]
			generated++
			return candidate, nil
		}),
	)
	persona, err := service.CreatePersona(context.Background(), ownerID, application.CreatePersonaCommand{DisplayName: "retry"}, application.PersonaCommandMeta{IdempotencyKey: "retry-key", CommandDigest: "retry-digest"})
	if err != nil {
		t.Fatal(err)
	}
	if persona.PersonaID != candidates[2] || generated != 3 {
		t.Fatalf("persona=%+v generated=%d", persona, generated)
	}

	commands = &identityRetryCommands{failures: []error{personaports.ErrPersonaQuotaReached}}
	generated = 0
	service = application.NewPersonaService(runtime, commands, identityRetryProjector{}, readinessProfileStore{runtime: runtime}, noOpProfileCache{}, application.WithPersonaIdentityGenerator(func(string) (string, error) { generated++; return candidates[0], nil }))
	_, err = service.CreatePersona(context.Background(), ownerID, application.CreatePersonaCommand{DisplayName: "no retry"}, application.PersonaCommandMeta{IdempotencyKey: "quota-key", CommandDigest: "quota-digest"})
	if err == nil || generated != 1 {
		t.Fatalf("non-identity failure retried: generated=%d err=%v", generated, err)
	}
}

func TestCreatePersonaIdentityCollisionBudgetExhaustionIsTyped(t *testing.T) {
	runtime, ownerID, _ := newReadinessPersonaRuntime(t)
	commands := &identityRetryCommands{failures: []error{
		personaports.ErrPersonaIdentityConflict,
		personaports.ErrPersonaIdentityConflict,
		personaports.ErrPersonaIdentityConflict,
	}}
	generated := 0
	service := application.NewPersonaService(runtime, commands, identityRetryProjector{}, readinessProfileStore{runtime: runtime}, noOpProfileCache{}, application.WithPersonaIdentityGenerator(func(string) (string, error) {
		generated++
		return fmt.Sprintf("us_01_0001_01j00000000000000000000%03d", generated), nil
	}))
	_, err := service.CreatePersona(context.Background(), ownerID, application.CreatePersonaCommand{DisplayName: "exhaust"}, application.PersonaCommandMeta{IdempotencyKey: "exhaust-key", CommandDigest: "exhaust-digest"})
	if !errors.Is(err, runtimeid.ErrAllocationBudgetExhausted) || generated != runtimeid.AllocationAttempts {
		t.Fatalf("generated=%d err=%v", generated, err)
	}
}
