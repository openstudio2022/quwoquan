// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/persona-management/spec.md#gwt-003
// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/profile-read-update/spec.md#gwt-001
// readiness_case: create-persona-api
// readiness_case: update-persona-api
// readiness_case: apply-persona-profile-sync-api
// readiness_case: retire-persona-api
// readiness_case: activate-persona-api
// readiness_case: update-user-profile-api
package api_integration

import (
	"context"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	application "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	useridentity "quwoquan_service/services/user-service/internal/account/user_account/domain/user/identity"
	usermodel "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	userpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/user/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/persona_management/persona/infrastructure/persona/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type personaOperationCache struct{}

func (personaOperationCache) Get(context.Context, string) (*usermodel.FullSnapshot, error) {
	return nil, nil
}
func (personaOperationCache) Set(context.Context, string, *usermodel.FullSnapshot) error { return nil }
func (personaOperationCache) Del(context.Context, string) error                          { return nil }

type personaOperationEvents struct{}

func (personaOperationEvents) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func personaOperationIdentity(t *testing.T) (string, string) {
	t.Helper()
	owner, err := useridentity.NewOwnerID("ph", "01j00000000000000000000020")
	if err != nil {
		t.Fatalf("build owner identity: %v", err)
	}
	persona, err := useridentity.NewPersonaID(owner.LogicalShardHex(), "01j00000000000000000000021")
	if err != nil {
		t.Fatalf("build persona identity: %v", err)
	}
	return owner.String(), persona.String()
}

func personaOperationMeta(key string) application.PersonaCommandMeta {
	return application.PersonaCommandMeta{IdempotencyKey: key, CommandDigest: "sha256:cc4c9a72efb00ef0376136712bc233e71e6a4f7692a302526c780fc41e7771f8"}
}

func TestPersonaOperationsCommitStateReceiptOutboxAndProjection(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		ownerID, primaryID := personaOperationIdentity(t)
		if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, primaryID); err != nil {
			t.Fatalf("seed owner and primary Persona: %v", err)
		}
		profiles := accountpersistence.NewPgProfileStore(pool)
		personas := userpersistence.NewPgPersonaStore(pool)
		commands, err := personapersistence.NewPersonaCommandPostgresStore(pool)
		if err != nil {
			t.Fatalf("construct Persona command store: %v", err)
		}
		projector, err := accountpersistence.NewPersonaProfileProjector(pool)
		if err != nil {
			t.Fatalf("construct Persona profile projector: %v", err)
		}
		service := application.NewPersonaService(
			personas, commands, projector, profiles, personaOperationCache{},
		)

		secondary, err := service.CreatePersona(ctx, ownerID, application.CreatePersonaCommand{
			DisplayName: "Secondary Persona",
		}, personaOperationMeta("create-secondary"))
		if err != nil {
			t.Fatalf("CreatePersona: %v", err)
		}
		updatedName := "Updated Secondary"
		updated, err := service.UpdatePersona(ctx, ownerID, secondary.PersonaID, application.UpdatePersonaCommand{
			DisplayName: &updatedName,
		}, personaOperationMeta("update-secondary"))
		if err != nil || updated.DisplayName != updatedName {
			t.Fatalf("UpdatePersona persona=%+v err=%v", updated, err)
		}
		syncResult, err := service.ApplyPersonaProfileSync(ctx, ownerID, primaryID, application.PersonaProfileSyncOptions{
			ApplyScope:    "selected_subjects",
			SyncTargetIDs: []string{secondary.PersonaID},
			FieldsMask:    []string{"displayName"},
		}, personaOperationMeta("sync-secondary"))
		if err != nil || syncResult.AppliedCount != 1 {
			t.Fatalf("ApplyPersonaProfileSync result=%+v err=%v", syncResult, err)
		}

		retireCandidate, err := service.CreatePersona(ctx, ownerID, application.CreatePersonaCommand{
			DisplayName: "Retire Candidate",
		}, personaOperationMeta("create-retire-candidate"))
		if err != nil {
			t.Fatalf("CreatePersona retire candidate: %v", err)
		}
		retired, err := service.RetirePersona(ctx, ownerID, retireCandidate.PersonaID, personaOperationMeta("retire-candidate"))
		if err != nil || retired["allowed"] != true {
			t.Fatalf("RetirePersona result=%+v err=%v", retired, err)
		}
		if err := service.ActivatePersona(ctx, ownerID, secondary.PersonaID, personaOperationMeta("activate-secondary")); err != nil {
			t.Fatalf("ActivatePersona: %v", err)
		}

		profileService, err := application.NewProfileService(
			profiles, personas, commands, projector, personaOperationCache{}, personaOperationEvents{}, nil,
		)
		if err != nil {
			t.Fatalf("construct ProfileService: %v", err)
		}
		profileName := "Profile Operation Name"
		profile, err := profileService.UpdateProfile(ctx, ownerID, application.ProfileUpdateCommand{
			DisplayName: &profileName,
		}, personaOperationMeta("update-user-profile"))
		if err != nil || profile.Nickname != profileName {
			t.Fatalf("UpdateUserProfile profile=%+v err=%v", profile, err)
		}

		var activePersonaID, activeDisplayName string
		if err := pool.QueryRow(ctx, `SELECT persona_id, display_name FROM personas WHERE user_id=$1 AND is_active=true`, ownerID).Scan(&activePersonaID, &activeDisplayName); err != nil {
			t.Fatalf("read active Persona: %v", err)
		}
		if activePersonaID != secondary.PersonaID || activeDisplayName != profileName {
			t.Fatalf("active Persona id=%q display=%q", activePersonaID, activeDisplayName)
		}
		var retiredStatus string
		if err := pool.QueryRow(ctx, `SELECT status FROM personas WHERE persona_id=$1`, retireCandidate.PersonaID).Scan(&retiredStatus); err != nil || retiredStatus != "retired" {
			t.Fatalf("retired Persona status=%q err=%v", retiredStatus, err)
		}
		var receiptCount, outboxCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_command_receipts`).Scan(&receiptCount); err != nil {
			t.Fatalf("read Persona receipts: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM personas_outbox`).Scan(&outboxCount); err != nil {
			t.Fatalf("read Persona outbox: %v", err)
		}
		if receiptCount < 7 || outboxCount < 7 {
			t.Fatalf("Persona packet receipts=%d outbox=%d", receiptCount, outboxCount)
		}
	})
}
