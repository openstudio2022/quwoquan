package support

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	appealhttp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/adapters/inbound/http"
	appealapp "quwoquan_service/services/user-service/internal/account/account_appeal_intake/application"
	appealmodel "quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
	appealports "quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/ports"
	appealidentity "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/identity"
	appealpersistence "quwoquan_service/services/user-service/internal/account/account_appeal_intake/infrastructure/persistence"
	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengepersistence "quwoquan_service/services/user-service/internal/account/authentication_challenge/infrastructure/persistence"
	credentialapp "quwoquan_service/services/user-service/internal/account/credential_binding/application"
	credentialpersistence "quwoquan_service/services/user-service/internal/account/credential_binding/infrastructure/persistence"
	userhttp "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
	useraccountapp "quwoquan_service/services/user-service/internal/account/user_account/application"
	useraccountpersistence "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/persistence"
)

var accountEnforcementTokenConfig = rtauth.TokenConfig{
	Secret:       []byte("account-enforcement-api-integration-secret-v1"),
	Issuer:       "https://auth.quwoquan.test",
	Audience:     "quwoquan-api",
	Type:         rtauth.TokenTypeAccess,
	TokenVersion: 1,
	TTL:          30 * time.Minute,
	ClockSkew:    30 * time.Second,
}

// AccountEnforcementRuntime exposes the real UserAccount HTTP boundary backed
// by the caller-provided PostgreSQL pool. It is intentionally narrow: test
// setup owns the listener, while migrations, stores, application facade,
// authorization middleware and handler are the same implementations used by
// the User service composition.
type AccountEnforcementRuntime struct {
	server                 *httptest.Server
	enforcementCredentials rtauth.ServiceAuthorizationProvider
	appealCredentials      rtauth.ServiceAuthorizationProvider
	appealStore            *appealpersistence.PostgresStore
}

func StartAccountEnforcementRuntime(
	ctx context.Context,
	pool *pgxpool.Pool,
) (*AccountEnforcementRuntime, error) {
	if pool == nil {
		return nil, fmt.Errorf("UserAccount enforcement runtime requires PostgreSQL")
	}
	if err := useraccountpersistence.RunManagedMigrations(ctx, pool); err != nil {
		return nil, fmt.Errorf("run User service managed migrations: %w", err)
	}

	credentialStore, err := credentialpersistence.NewPostgresStore(pool)
	if err != nil {
		return nil, err
	}
	challengeStore, err := challengepersistence.NewPostgresStore(pool)
	if err != nil {
		return nil, err
	}
	challenges := challengeapp.NewAuthenticationChallengeCommandFacade(
		challengeStore,
		challengeapp.OTPCredentialVerifier{},
	)
	appealStore, err := appealpersistence.NewPostgresStore(pool)
	if err != nil {
		return nil, err
	}
	appealFacade := appealapp.NewCommandFacade(
		appealStore,
		appealidentity.NewChallengeVerifier(challenges, credentialStore),
		nil,
	)
	appealHandler, err := appealhttp.NewHandler(appealFacade)
	if err != nil {
		return nil, err
	}
	userHandler, err := userhttp.NewUserHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		credentialapp.NewCredentialQueryFacade(credentialStore),
		nil,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("compose UserAccount handler: %w", err)
	}
	enforcementStore, err := useraccountpersistence.NewEnforcementStore(pool)
	if err != nil {
		return nil, err
	}
	userHandler.WithAccountEnforcement(
		useraccountapp.NewAccountEnforcementCommandFacade(enforcementStore),
	)
	userHandler.WithAccountSecurityReader(enforcementStore)

	serviceMux := http.NewServeMux()
	userHandler.RegisterRoutes(serviceMux)
	appealHandler.RegisterRoutes(serviceMux)
	descriptors := accountEnforcementIntegrationDescriptors()
	authorized := rtauth.EnforceGeneratedOperationAuthorization(descriptors)(
		userHandler.WrapAccountSecurity(serviceMux),
	)
	verifier, err := rtauth.NewHS256Verifier(accountEnforcementTokenConfig)
	if err != nil {
		return nil, err
	}
	enforcementCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accountEnforcementTokenConfig,
		"product-ops-service",
		[]string{"user.account.enforcement.write"},
	)
	if err != nil {
		return nil, err
	}
	appealCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accountEnforcementTokenConfig,
		"product-ops-service",
		[]string{"user.account.appeal_intake.claim"},
	)
	if err != nil {
		return nil, err
	}
	server := httptest.NewServer(rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier: verifier,
	})(authorized))
	return &AccountEnforcementRuntime{
		server: server, enforcementCredentials: enforcementCredentials,
		appealCredentials: appealCredentials, appealStore: appealStore,
	}, nil
}

func accountEnforcementIntegrationDescriptors() []rtauth.OperationSecurityDescriptor {
	descriptors := operationsecurity.ForDomain("user")
	for index := range descriptors {
		switch descriptors[index].CanonicalOperationID {
		case "user.user_account.SuspendAccount",
			"user.user_account.RestoreAccount":
			// Canonical production descriptors remain blocked until the external
			// commercial evidence named by their contracts exists. This test-only
			// runtime activates copied descriptors so Product Ops can exercise the
			// real authenticated HTTP adapter, User handler and PostgreSQL stores.
			descriptors[index].CommercialStatus = "ready"
		}
	}
	return descriptors
}

func (runtime *AccountEnforcementRuntime) BaseURL() string {
	return runtime.server.URL
}

func (runtime *AccountEnforcementRuntime) HTTPClient() *http.Client {
	return runtime.server.Client()
}

func (runtime *AccountEnforcementRuntime) Credentials() rtauth.ServiceAuthorizationProvider {
	return runtime.enforcementCredentials
}

func (runtime *AccountEnforcementRuntime) AppealCredentials() rtauth.ServiceAuthorizationProvider {
	return runtime.appealCredentials
}

func (runtime *AccountEnforcementRuntime) Close() {
	if runtime != nil && runtime.server != nil {
		runtime.server.Close()
	}
}

// SubmitAppealIntakeFixture creates a real persisted intake for cross-service
// API integration after the target account has been suspended. Identity/OTP is
// covered by User-owned tests; this helper deliberately bypasses only that
// external delivery setup, never the intake store or claim boundary.
func (runtime *AccountEnforcementRuntime) SubmitAppealIntakeFixture(
	ctx context.Context,
	accountID string,
	seed string,
) (string, error) {
	if runtime == nil || runtime.appealStore == nil ||
		strings.TrimSpace(accountID) == "" || strings.TrimSpace(seed) == "" {
		return "", fmt.Errorf("account appeal fixture requires runtime, account and seed")
	}
	now := time.Now().UTC()
	credential := "appeal_credential_fixture_" + stableTestDigest(seed)[:32]
	credentialDigest := stableTestDigest(credential)
	challengeID := "appeal_ch_fixture_" + stableTestDigest("challenge\x00" + seed)[:32]
	intakeRef := "appeal_intake_" + stableTestDigest("intake\x00" + seed)[:32]
	_, err := runtime.appealStore.IssueCredential(ctx, appealports.IssueCredentialCommit{
		CredentialID:     "appeal_credential_" + credentialDigest[:24],
		CredentialDigest: credentialDigest,
		ChallengeID:      challengeID,
		AccountID:        strings.TrimSpace(accountID),
		IssuedAt:         now,
		ExpiresAt:        now.Add(appealmodel.CredentialTTL),
		DeleteAfter: now.Add(appealmodel.CredentialTTL).
			Add(appealmodel.CredentialAuditRetention),
	})
	if err != nil {
		return "", err
	}
	result, err := runtime.appealStore.Submit(ctx, appealports.SubmitCommit{
		CredentialDigest: credentialDigest,
		IntakeRef:        intakeRef,
		IdempotencyKey:   "fixture-submit-" + stableTestDigest(seed)[:24],
		CommandDigest:    stableTestDigest("submit\x00" + credentialDigest),
		SubmittedAt:      now,
		DeleteAfter:      now.Add(appealmodel.IntakeRetention),
	})
	if err != nil {
		return "", err
	}
	return result.Intake.State().IntakeRef, nil
}

func stableTestDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return hex.EncodeToString(sum[:])
}

func CreateAccount(
	ctx context.Context,
	pool *pgxpool.Pool,
	accountID string,
	nickname string,
) error {
	phoneHash := sha256.Sum256([]byte(accountID))
	_, err := pool.Exec(ctx, `
INSERT INTO user_profiles (
  user_id, account_state, identity_origin, logical_shard,
  anonymous_retention_policy, phone, nickname, nickname_customized,
  avatar_url, avatar_asset_id, avatar_version, background_url, bio,
  identity_tags, gender, region, owner_display_name,
  profile_version, persona_count, created_at, updated_at
) VALUES (
  $1, 'active', 'migrated_seed', 0, 'preserve', $2, $3, false,
  '', '', 0, '', '', '', '', '', '', 1, 1, NOW(), NOW()
)`, accountID, fmt.Sprintf("t_%x", phoneHash[:8]), nickname)
	if err != nil {
		return fmt.Errorf("create UserAccount integration fixture: %w", err)
	}
	return nil
}
