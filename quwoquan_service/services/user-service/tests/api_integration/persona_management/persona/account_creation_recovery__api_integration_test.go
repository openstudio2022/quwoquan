// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-006
package api_integration

import (
	"context"
	"errors"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"

	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	persistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	personaports "quwoquan_service/services/user-service/internal/persona_management/persona/domain/persona/ports"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

func TestAccountCreationRecoveryStoreKeepsStableIdentityAndMonotonicSteps(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		store, err := persistence.NewAccountCreationRecoveryPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		candidate := application.AccountCreationFlow{
			FlowID: "account-create-flow-1", IntentDigest: "digest-1",
			OwnerID: "owner-stable", PersonaID: "persona-stable",
			DefaultNickname: "stable-name", IdentityOrigin: "phone",
		}
		first, err := store.Begin(ctx, candidate)
		if err != nil {
			t.Fatal(err)
		}
		if first.OwnerID != candidate.OwnerID || first.PersonaID != candidate.PersonaID {
			t.Fatalf("first flow=%+v", first)
		}

		replayCandidate := candidate
		replayCandidate.OwnerID = "owner-new-candidate"
		replayCandidate.PersonaID = "persona-new-candidate"
		replayCandidate.DefaultNickname = "new-name"
		replayed, err := store.Begin(ctx, replayCandidate)
		if err != nil {
			t.Fatal(err)
		}
		if replayed.OwnerID != candidate.OwnerID || replayed.PersonaID != candidate.PersonaID || replayed.DefaultNickname != candidate.DefaultNickname {
			t.Fatalf("replay changed stable flow identity: %+v", replayed)
		}
		if _, err := store.Begin(ctx, application.AccountCreationFlow{
			FlowID: candidate.FlowID, IntentDigest: "different-intent",
			OwnerID: candidate.OwnerID, PersonaID: candidate.PersonaID,
			DefaultNickname: candidate.DefaultNickname, IdentityOrigin: candidate.IdentityOrigin,
		}); !errors.Is(err, application.ErrAccountCreationFlowConflict) {
			t.Fatalf("different intent error=%v", err)
		}

		steps := []application.AccountCreationStep{
			application.AccountCreationAccountCommitted,
			application.AccountCreationPersonaCommitted,
			application.AccountCreationProfileProjected,
			application.AccountCreationCredentialBound,
		}
		for index, step := range steps {
			if err := store.MarkStep(ctx, candidate.FlowID, step); err != nil {
				t.Fatalf("MarkStep(%s): %v", step, err)
			}
			current, found, err := store.Load(ctx, candidate.FlowID)
			if err != nil || !found {
				t.Fatalf("Load after step %s: found=%v err=%v", step, found, err)
			}
			if current.Completed != (index == len(steps)-1) {
				t.Fatalf("completed=%v after %d steps", current.Completed, index+1)
			}
		}
		if err := store.MarkStep(ctx, candidate.FlowID, application.AccountCreationPersonaCommitted); err != nil {
			t.Fatal(err)
		}
		terminal, _, err := store.Load(ctx, candidate.FlowID)
		if err != nil || !terminal.Completed {
			t.Fatalf("terminal replay lost completion: %+v err=%v", terminal, err)
		}
	})
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-004
func TestPersonaCommandStoreClassifiesOnlyIdentityConstraintAsRetryable(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const ownerID = "identity-classification-owner"
		profileStore := persistence.NewPgProfileStore(pool)
		if err := profileStore.CreateAccount(ctx, userports.UserAccountCreate{
			UserID: ownerID, AccountState: "active", IdentityOrigin: "api_integration",
			LogicalShard: 1, AnonymousRetentionPolicy: "preserve", PersonaCount: 1,
		}); err != nil {
			t.Fatal(err)
		}
		store, err := personapersistence.NewPersonaCommandPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		newPersona := func(id, handle string) *usermodel.Persona {
			return &usermodel.Persona{
				PersonaID: id, UserID: ownerID, UserHandle: handle, DisplayName: id,
				IdentityTags: []string{}, IsolationLevel: "open", Status: "active",
				InheritsProfileFromOwner: true, OverriddenProfileFields: []string{},
			}
		}
		firstID := "identity-classification-persona"
		if _, err := store.CommitCreate(ctx, newPersona(firstID, "identity-handle-1"), personaports.PersonaCommandMeta{IdempotencyKey: "identity-key-1", CommandDigest: "digest-1"}); err != nil {
			t.Fatal(err)
		}
		if _, err := store.CommitCreate(ctx, newPersona(firstID, "identity-handle-2"), personaports.PersonaCommandMeta{IdempotencyKey: "identity-key-2", CommandDigest: "digest-2"}); !errors.Is(err, personaports.ErrPersonaIdentityConflict) {
			t.Fatalf("duplicate persona id error=%v", err)
		}
		if _, err := store.CommitCreate(ctx, newPersona("identity-classification-other", "identity-handle-1"), personaports.PersonaCommandMeta{IdempotencyKey: "identity-key-3", CommandDigest: "digest-3"}); !errors.Is(err, userports.ErrPersonaHandleConflict) {
			t.Fatalf("duplicate handle error=%v", err)
		}
	})
}
