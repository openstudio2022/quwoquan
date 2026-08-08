// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
// readiness_case: resolve-capability-grant-api
package capability_grant_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	grantadapter "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/adapters/inbound/runtime"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantpersistence "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/persistence"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

func TestRuntimeEntrypointBuildsRedactedConnectorCandidateAndResolves(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	redisRuntime, err := testinfra.StartRealRedis(startupCtx)
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := redisRuntime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(startupCtx, 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	redisRouter, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		t.Fatalf("new Redis router: %v", err)
	}
	t.Cleanup(func() { _ = redisRouter.Close() })
	store, err := grantpersistence.NewRedisSessionStore(redisRouter.Scene("general"))
	if err != nil {
		t.Fatal(err)
	}

	now := time.Date(2026, time.August, 6, 6, 0, 0, 0, time.UTC)
	reader := connectorReader{values: []connectionmodel.Connection{{
		ConnectionID:                 "connection-calendar-1",
		AccountID:                    "account-1",
		ConnectorID:                  "calendar",
		GrantedCapabilities:          []string{"calendar.event.create"},
		Status:                       connectionmodel.StatusActive,
		CredentialRef:                "must-not-cross-capability-boundary",
		ProviderAccountSubjectDigest: apiDigest("provider-account"),
		FreshnessAt:                  now.Add(-time.Minute),
		Revision:                     3,
	}}}
	unavailable := grantcandidate.NewUnavailableSources("not configured in adapter test")
	resolver := grantresolver.NewCandidateResolver(
		unavailable,
		grantcandidate.NewConnectorReaderSource(
			reader,
			connectorDefinitionReader{},
			func() time.Time { return now },
		),
		unavailable,
		unavailable,
		func() time.Time { return now },
	)
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	decision, err := grantadapter.NewMiddleware(
		grantapp.NewCapabilityGrantSessionFacade(resolver, store),
	).ResolveConnectorGrant(
		context.Background(),
		authorization,
		grantapp.ConnectorResolutionRequest{
			ResolutionID:   "resolution-calendar-1",
			CapabilityKey:  "calendar.event.create",
			SurfaceKind:    "personal",
			ConnectionRefs: []string{"connection-calendar-1"},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if !decision.Allowed || decision.ConnectionID != "connection-calendar-1" ||
		decision.ExpiresAt == nil {
		t.Fatalf("decision=%+v", decision)
	}
	persisted, err := store.Load(context.Background(), "resolution-calendar-1")
	if err != nil || persisted.BindingKind != grantmodel.BindingUserConnector ||
		persisted.CapabilityKey != "calendar.event.create" ||
		!persisted.ExpiresAt.Equal(now.Add(grantmodel.GrantTTL)) {
		t.Fatalf("persisted session=%+v err=%v", persisted, err)
	}
}

func TestRuntimeEntrypointFailsClosedWhenPrioritySourceIsMissing(t *testing.T) {
	now := time.Date(2026, time.August, 6, 6, 5, 0, 0, time.UTC)
	resolver := grantresolver.NewCandidateResolver(
		nil,
		nil,
		nil,
		nil,
		func() time.Time { return now },
	)
	_, err := grantapp.NewCapabilityGrantSessionFacade(
		resolver,
		&apiSessionStore{},
	).Resolve(
		context.Background(),
		grantmodel.Requirement{
			ResolutionID:    "resolution-provider-1",
			CapabilityKey:   "location.poi.search",
			BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
		},
	)
	if !errors.Is(err, grantapp.ErrCandidateSourceUnavailable) {
		t.Fatalf("missing source error=%v", err)
	}
}

type connectorReader struct {
	values []connectionmodel.Connection
}

func (reader connectorReader) Get(
	_ context.Context,
	accountID string,
	connectionID string,
) (connectionmodel.Connection, error) {
	for _, value := range reader.values {
		if value.AccountID == accountID && value.ConnectionID == connectionID {
			return value, nil
		}
	}
	return connectionmodel.Connection{}, connectionmodel.ErrNotFound
}

func (reader connectorReader) List(
	_ context.Context,
	accountID string,
	limit int,
) ([]connectionmodel.Connection, error) {
	if accountID == "" || limit <= 0 {
		return nil, connectionmodel.ErrInvalidArgument
	}
	return append([]connectionmodel.Connection(nil), reader.values...), nil
}

type connectorDefinitionReader struct{}

func (connectorDefinitionReader) Get(
	context.Context,
	string,
) (definitionmodel.Definition, error) {
	return definitionmodel.Definition{
		ConnectorID:           "calendar",
		Capabilities:          []string{"calendar.event.create"},
		SupportedSurfaceKinds: []string{"personal"},
		Status:                definitionmodel.StatusActive,
		ReleaseDigest:         apiDigest("calendar-contract"),
	}, nil
}

func (connectorDefinitionReader) List(
	context.Context,
	string,
	int,
) ([]definitionmodel.Definition, error) {
	value, _ := (connectorDefinitionReader{}).Get(context.Background(), "calendar")
	return []definitionmodel.Definition{value}, nil
}

type apiSessionStore struct {
	values []grantmodel.ResolvedCapabilityGrant
}

func (store *apiSessionStore) Save(
	_ context.Context,
	grant grantmodel.ResolvedCapabilityGrant,
) error {
	store.values = append(store.values, grant)
	return nil
}

func (store *apiSessionStore) Load(
	_ context.Context,
	resolutionID string,
) (grantapp.StoredSession, error) {
	for _, grant := range store.values {
		if grant.ResolutionID != resolutionID || grant.ExpiresAt == nil {
			continue
		}
		bindingDigest, err := grantmodel.BindingDigest(grant)
		if err != nil {
			return grantapp.StoredSession{}, err
		}
		return grantapp.StoredSession{
			ResolutionID:       grant.ResolutionID,
			AccountDigest:      grantmodel.OpaqueDigest(grant.AccountID),
			ServiceActorDigest: grant.ServiceActorDigest,
			CapabilityKey:      grant.CapabilityKey,
			SurfaceKind:        grant.SurfaceKind,
			BindingKind:        grant.BindingKind,
			BindingDigest:      bindingDigest,
			InputDigest:        grant.InputDigest,
			ConfirmationDigest: grant.ConfirmationDigest,
			PermitDigest:       grant.PermitDigest,
			IdempotencyDigest:  grant.IdempotencyDigest,
			ResolvedAt:         grant.ResolvedAt,
			ExpiresAt:          *grant.ExpiresAt,
		}, nil
	}
	return grantapp.StoredSession{}, grantapp.ErrCapabilityGrantSessionNotFound
}

func apiDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}
