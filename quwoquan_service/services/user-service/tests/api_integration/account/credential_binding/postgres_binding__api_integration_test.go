// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: list-credentials-api
// readiness_case: unbind-credential-api
// readiness_case: bind-phone-credential-api
// readiness_case: complete-federated-phone-binding-api
// readiness_case: bind-carrier-phone-credential-api
package api_integration

import (
	"context"
	"crypto/sha256"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	bindingapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	bindingmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	bindingports "quwoquan_service/services/user-service/internal/account/credential_binding/domain/ports"
	bindingpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	accountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
	usersupport "quwoquan_service/services/user-service/tests/support"
)

type apiCredentialAuditPublisher struct {
	eventID string
}

func (publisher *apiCredentialAuditPublisher) PublishCredentialAudit(
	_ context.Context,
	event bindingports.SecurityAuditEvent,
) error {
	publisher.eventID = event.EventID
	return nil
}

func TestCredentialBindingPostgresNaturalIdempotencyAndAuditMirror(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(
			ctx, pool, "binding-owner", "binding-persona",
		); err != nil {
			t.Fatalf("seed canonical CredentialBinding owner: %v", err)
		}
		store, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		facade := bindingapp.NewCredentialCommandFacade(store)
		credentialKey := fmt.Sprintf(
			"sha256:%x",
			sha256.Sum256([]byte("verified-phone:+8613800000000")),
		)
		command := bindingapp.BindCredentialCommand{
			CredentialType: bindingmodel.CredentialTypePhone,
			CredentialKey:  credentialKey, DisplayLabel: "手机",
		}
		first, err := facade.BindVerifiedCredential(ctx, "binding-owner", command)
		if err != nil {
			t.Fatal(err)
		}
		replayed, err := facade.BindVerifiedCredential(ctx, "binding-owner", command)
		if err != nil || !replayed.IdempotentReplay || replayed.Version != first.Version {
			t.Fatalf("CredentialBinding replay drift: first=%+v replay=%+v err=%v", first, replayed, err)
		}
		var stateCount, eventCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1`, "binding-owner").Scan(&stateCount); err != nil {
			t.Fatal(err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings_outbox WHERE aggregate_id IN (SELECT id FROM credential_bindings WHERE owner_id=$1)`, "binding-owner").Scan(&eventCount); err != nil {
			t.Fatal(err)
		}
		if stateCount != 1 || eventCount != 1 {
			t.Fatalf("CredentialBinding packet mismatch: state=%d outbox=%d", stateCount, eventCount)
		}
		auditPublisher := &apiCredentialAuditPublisher{}
		auditRelay, err := bindingapp.NewSecurityAuditRelay(store, auditPublisher)
		if err != nil {
			t.Fatal(err)
		}
		if published, err := auditRelay.Drain(ctx, 10); err != nil || published != 1 {
			t.Fatalf("CredentialBinding audit relay published=%d err=%v", published, err)
		}
		if auditPublisher.eventID == "" {
			t.Fatal("CredentialBinding audit relay did not hand off the committed event")
		}
		var publishedCount int
		if err := pool.QueryRow(ctx, `
SELECT COUNT(*) FROM credential_bindings_outbox
WHERE aggregate_id IN (SELECT id FROM credential_bindings WHERE owner_id=$1)
  AND published_at IS NOT NULL`, "binding-owner").Scan(&publishedCount); err != nil {
			t.Fatal(err)
		}
		if publishedCount != 1 {
			t.Fatalf("CredentialBinding audit mirror checkpoint=%d, want 1", publishedCount)
		}
	})
}

func TestCredentialBindingPostgresQueryAndUnbindUseCommittedState(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		if err := usersupport.SeedAccountPersona(
			ctx, pool, "binding-readiness-owner", "binding-readiness-persona",
		); err != nil {
			t.Fatalf("seed canonical CredentialBinding owner: %v", err)
		}
		store, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatal(err)
		}
		commands := bindingapp.NewCredentialCommandFacade(store)
		queries := bindingapp.NewCredentialQueryFacade(store)
		actorContext := operation.WithContext(ctx, operation.Context{
			OperationID: "user.credential_binding.ListCredentials",
			RequestID:   "credential-readiness-request",
			TraceID:     "credential-readiness-trace",
			Actor: operation.ActorContext{
				AccountID: "binding-readiness-owner",
			},
		})
		for _, command := range []bindingapp.BindCredentialCommand{
			{
				CredentialType: bindingmodel.CredentialTypePhone,
				CredentialKey:  "sha256:672e81ba50de4f3c01a34e9dfe3ddca34cddfbd18bf9fbaa2549746c224a97ef",
				DisplayLabel:   "138****0001",
			},
			{
				CredentialType: bindingmodel.CredentialTypeFederatedSlotA,
				CredentialKey:  "sha256:da46eb4c4d1ce1f0e6ae9892255b01d79e67641909097d3f6fba25ee29b34eeb",
				DisplayLabel:   "Federated Account",
			},
		} {
			if _, err := commands.BindVerifiedCredential(actorContext, "binding-readiness-owner", command); err != nil {
				t.Fatalf("seed CredentialBinding: %v", err)
			}
		}
		items, err := queries.ListCredentials(actorContext)
		if err != nil || len(items) != 2 {
			t.Fatalf("ListCredentials items=%+v err=%v", items, err)
		}
		revoked, err := commands.UnbindCredential(actorContext, bindingapp.UnbindCredentialCommand{
			CredentialType: bindingmodel.CredentialTypeFederatedSlotA,
		})
		if err != nil || revoked.IsActive {
			t.Fatalf("UnbindCredential result=%+v err=%v", revoked, err)
		}
		var activeCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1 AND is_active=true`, "binding-readiness-owner").Scan(&activeCount); err != nil || activeCount != 1 {
			t.Fatalf("active CredentialBinding count=%d err=%v", activeCount, err)
		}
	})
}

func TestBindPhoneCredentialVerifiesChallengeAndCommitsPostgresBinding(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			ownerID     = "binding-phone-owner"
			personaID   = "binding-phone-persona"
			phone       = "+8613800000101"
			otpCode     = "654321"
			challengeID = "otp-bind-phone-credential"
		)
		if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, personaID); err != nil {
			t.Fatalf("seed phone binding owner: %v", err)
		}
		bindingStore, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("credential store: %v", err)
		}
		challengeStore, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("challenge store: %v", err)
		}
		challengeCommands := challengeapp.NewAuthenticationChallengeCommandFacade(
			challengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
		destinationHash := challengeapp.SMSDestinationHash(phone)
		if _, err := challengeCommands.CreateChallenge(ctx, challengeapp.CreateChallengeCommand{
			ID:              challengeID,
			Purpose:         "bind_phone",
			Channel:         "sms",
			DestinationHash: destinationHash,
			SecretRef:       challengeapp.OTPSecretReference(challengeID, destinationHash, []byte(otpCode)),
			IdempotencyKey:  "bind-phone-credential-readiness",
			ExpiresAt:       time.Now().UTC().Add(5 * time.Minute),
		}); err != nil {
			t.Fatalf("seed bind-phone challenge: %v", err)
		}
		service := accountapp.NewAuthService(
			accountpersistence.NewPgProfileStore(pool),
			nil,
			bindingStore,
			nil,
			nil,
			accountapp.WithCredentialCommands(bindingapp.NewCredentialCommandFacade(bindingStore)),
			accountapp.WithAuthenticationChallenges(challengeCommands),
		)

		result, err := service.BindPhoneCredential(
			ctx,
			ownerID,
			phone,
			otpCode,
			"138****0101",
		)
		if err != nil {
			t.Fatalf("BindPhoneCredential: %v", err)
		}
		binding, found, err := bindingStore.LoadByOwnerAndType(
			ctx,
			ownerID,
			bindingmodel.CredentialTypePhone,
		)
		if err != nil || !found ||
			binding.State().CredentialKey != phone ||
			!result.IsActive {
			t.Fatalf("phone binding state=%+v result=%+v found=%v err=%v", binding.State(), result, found, err)
		}
		var persistedPhone string
		if err := pool.QueryRow(ctx, `SELECT phone FROM user_profiles WHERE user_id=$1`, ownerID).Scan(&persistedPhone); err != nil {
			t.Fatalf("read promoted owner phone: %v", err)
		}
		if persistedPhone != phone {
			t.Fatalf("promoted owner phone=%q want=%q", persistedPhone, phone)
		}
	})
}

func TestBindCarrierPhoneCredentialUsesResolverRegistrationAndPostgresBinding(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			ownerID   = "binding-carrier-owner"
			personaID = "binding-carrier-persona"
			deviceID  = "carrier-device-1"
			phone     = "+8613800000102"
		)
		if err := usersupport.SeedAccountPersona(ctx, pool, ownerID, personaID); err != nil {
			t.Fatalf("seed carrier binding owner: %v", err)
		}
		bindingStore, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("credential store: %v", err)
		}
		registrationStore, err := registrationpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("device registration store: %v", err)
		}
		cipher, err := registrationpersistence.NewAESGCMTokenCipher(make([]byte, 32))
		if err != nil {
			t.Fatalf("device registration cipher: %v", err)
		}
		service := accountapp.NewAuthService(
			accountpersistence.NewPgProfileStore(pool),
			nil,
			bindingStore,
			nil,
			nil,
			accountapp.WithCredentialCommands(bindingapp.NewCredentialCommandFacade(bindingStore)),
			accountapp.WithCarrierPhoneResolver(apiCredentialCarrierResolver{phone: phone}),
			accountapp.WithDeviceRegistration(registrationapp.NewCommandFacade(registrationStore, cipher)),
		)

		result, err := service.BindCarrierPhoneCredential(
			ctx,
			ownerID,
			"opaque-carrier-proof",
			deviceID,
			"ios",
			"",
		)
		if err != nil {
			t.Fatalf("BindCarrierPhoneCredential: %v", err)
		}
		binding, found, err := bindingStore.LoadByOwnerAndType(
			ctx,
			ownerID,
			bindingmodel.CredentialTypeCarrierPhone,
		)
		if err != nil || !found || binding.State().CredentialKey != phone || !result.IsActive {
			t.Fatalf("carrier binding state=%+v result=%+v found=%v err=%v", binding.State(), result, found, err)
		}
		var registrationCount int
		if err := pool.QueryRow(
			ctx,
			`SELECT COUNT(*) FROM user_devices WHERE account_id=$1 AND device_id=$2`,
			ownerID,
			deviceID,
		).Scan(&registrationCount); err != nil {
			t.Fatalf("read carrier device registration: %v", err)
		}
		if registrationCount != 1 {
			t.Fatalf("carrier device registration count=%d want=1", registrationCount)
		}
	})
}

func TestCompleteFederatedPhoneBindingCommitsAtomicPostgresPacket(t *testing.T) {
	usersupport.WithUserPostgres(t, func(ctx context.Context, pool *pgxpool.Pool) {
		const (
			phone       = "+8613800000103"
			otpCode     = "123456"
			challengeID = "otp-complete-federated-binding"
		)
		bindingStore, err := bindingpersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("credential store: %v", err)
		}
		issued, err := bindingStore.IssueFederatedPhoneBindingTicket(
			ctx,
			bindingapp.IssueFederatedPhoneBindingTicket{
				Provider:         bindingmodel.FederatedProviderSlotA,
				CredentialType:   bindingmodel.CredentialTypeFederatedSlotA,
				CredentialKey:    "federated-subject-readiness",
				DisplayName:      "Federated Readiness",
				DeviceID:         "federated-device-1",
				Platform:         "ios",
				AppVersion:       "1.0.0",
				AgreementVersion: "agreement-v1",
				PrivacyVersion:   "privacy-v1",
				ExpiresAt:        time.Now().UTC().Add(3 * time.Minute),
			},
		)
		if err != nil {
			t.Fatalf("issue federated binding ticket: %v", err)
		}
		ticket, err := bindingStore.ResolveFederatedPhoneBindingTicket(ctx, issued.Opaque)
		if err != nil {
			t.Fatalf("resolve federated binding ticket: %v", err)
		}
		challengeStore, err := challengepersistence.NewPostgresStore(pool)
		if err != nil {
			t.Fatalf("challenge store: %v", err)
		}
		challengeCommands := challengeapp.NewAuthenticationChallengeCommandFacade(
			challengeStore,
			challengeapp.OTPCredentialVerifier{},
		)
		destinationHash := challengeapp.SMSDestinationHash(phone)
		if _, err := challengeCommands.CreateChallenge(ctx, challengeapp.CreateChallengeCommand{
			ID:               challengeID,
			Purpose:          "bind_phone",
			Channel:          "sms",
			DestinationHash:  destinationHash,
			SecretRef:        challengeapp.OTPSecretReference(challengeID, destinationHash, []byte(otpCode)),
			BindingTicketRef: ticket.ID,
			IdempotencyKey:   "complete-federated-binding-readiness",
			ExpiresAt:        time.Now().UTC().Add(5 * time.Minute),
		}); err != nil {
			t.Fatalf("seed federated binding challenge: %v", err)
		}
		shards, err := accountapp.LoadDefaultShardDirectory()
		if err != nil {
			t.Fatalf("load shard directory: %v", err)
		}
		projector, err := accountpersistence.NewPersonaProfileProjector(pool)
		if err != nil {
			t.Fatalf("Persona profile projector: %v", err)
		}
		signer, err := rtauth.NewHS256Signer(rtauth.TokenConfig{
			Secret:       []byte("credential-binding-api-secret-32bytes"),
			Issuer:       "https://auth.quwoquan.test",
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
			accountapp.WithFederatedPhoneBindingTickets(bindingStore),
			accountapp.WithPersonaCommandPipeline(nil, projector),
			accountapp.WithAccessTokenSigner(signer),
		)

		grant, err := service.CompleteFederatedPhoneBinding(
			ctx,
			bindingapp.CompleteFederatedPhoneBindingCommand{
				BindingTicket:    issued.Opaque,
				Phone:            phone,
				OTPCode:          otpCode,
				ChallengeID:      challengeID,
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
		if grant == nil || grant.OwnerID == "" || grant.AccessToken == "" || grant.RefreshToken == "" {
			t.Fatalf("federated completion grant=%+v", grant)
		}
		var profileCount, bindingCount, sessionCount int
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM user_profiles WHERE user_id=$1`, grant.OwnerID).Scan(&profileCount); err != nil {
			t.Fatalf("count committed owner: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM credential_bindings WHERE owner_id=$1 AND is_active=true`, grant.OwnerID).Scan(&bindingCount); err != nil {
			t.Fatalf("count committed bindings: %v", err)
		}
		if err := pool.QueryRow(ctx, `SELECT COUNT(*) FROM account_sessions WHERE account_id=$1 AND status='active'`, grant.OwnerID).Scan(&sessionCount); err != nil {
			t.Fatalf("count committed session: %v", err)
		}
		if profileCount != 1 || bindingCount != 2 || sessionCount != 1 {
			t.Fatalf("federated packet counts profile=%d bindings=%d session=%d", profileCount, bindingCount, sessionCount)
		}
	})
}

type apiCredentialCarrierResolver struct {
	phone string
}

func (resolver apiCredentialCarrierResolver) ResolvePhone(
	_ context.Context,
	carrierToken string,
) (accountapp.VerifiedCarrierPhone, error) {
	if carrierToken != "opaque-carrier-proof" {
		return accountapp.VerifiedCarrierPhone{}, fmt.Errorf("unknown carrier proof")
	}
	return accountapp.VerifiedCarrierPhone{
		Phone:        resolver.phone,
		DisplayLabel: "138****0102",
	}, nil
}

var _ accountapp.CarrierPhoneResolver = apiCredentialCarrierResolver{}
