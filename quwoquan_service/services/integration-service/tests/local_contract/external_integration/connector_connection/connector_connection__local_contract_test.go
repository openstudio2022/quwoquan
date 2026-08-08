// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
// readiness_case: list-connector-connections-local
// readiness_case: get-connector-connection-local
// readiness_case: create-connector-connection-local
// readiness_case: revoke-connector-connection-local
// readiness_case: resolve-connector-capability-grant-local
package connector_connection_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	grantadapter "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/adapters/inbound/runtime"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionhttp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/adapters/inbound/http"
	connectionapp "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/application"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
	definitionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type definitionReader struct{ definition definitionmodel.Definition }

func (reader definitionReader) Get(context.Context, string) (definitionmodel.Definition, error) {
	return reader.definition, nil
}

func (reader definitionReader) List(context.Context, string, int) ([]definitionmodel.Definition, error) {
	return []definitionmodel.Definition{reader.definition}, nil
}

type grantVerifier struct{ grant connectionmodel.VerifiedGrant }

func (verifier grantVerifier) Verify(
	context.Context,
	string,
	definitionmodel.Definition,
	string,
	[]string,
) (connectionmodel.VerifiedGrant, error) {
	return verifier.grant, nil
}

type connectionStore struct {
	created connectionmodel.CreateCommand
	current connectionmodel.Connection
}

func (*connectionStore) Replay(
	context.Context,
	string,
	string,
	string,
	string,
) (connectionmodel.MutationResult, bool, error) {
	return connectionmodel.MutationResult{}, false, nil
}

func (store *connectionStore) Get(_ context.Context, accountID, connectionID string) (connectionmodel.Connection, error) {
	if store.current.AccountID != accountID || store.current.ConnectionID != connectionID {
		return connectionmodel.Connection{}, connectionmodel.ErrNotFound
	}
	return store.current, nil
}

func (store *connectionStore) List(_ context.Context, accountID string, _ int) ([]connectionmodel.Connection, error) {
	if store.current.AccountID != accountID {
		return nil, nil
	}
	return []connectionmodel.Connection{store.current}, nil
}

func (store *connectionStore) Create(_ context.Context, command connectionmodel.CreateCommand) (connectionmodel.MutationResult, error) {
	store.created = command
	store.current = connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: command.AccountID,
		ConnectorID: command.ConnectorID, GrantedCapabilities: command.GrantedCapabilities,
		Status: connectionmodel.StatusActive, CredentialRef: command.CredentialRef,
		ProviderAccountSubjectDigest: command.ProviderAccountSubjectDigest,
		GrantReceiptDigest:           command.GrantReceiptDigest, FreshnessAt: command.OccurredAt,
		Revision: 1, CreatedAt: command.OccurredAt, UpdatedAt: command.OccurredAt,
	}
	return connectionmodel.MutationResult{Connection: store.current}, nil
}

func (store *connectionStore) Revoke(_ context.Context, input connectionmodel.RevokeInput) (connectionmodel.MutationResult, error) {
	if store.current.AccountID != input.AccountID || store.current.ConnectionID != input.ConnectionID {
		return connectionmodel.MutationResult{}, connectionmodel.ErrNotFound
	}
	if store.current.Revision != input.ExpectedRevision {
		return connectionmodel.MutationResult{}, connectionmodel.ErrRevisionConflict
	}
	revokedAt := input.OccurredAt
	store.current.Status = connectionmodel.StatusRevoked
	store.current.CredentialRef = ""
	store.current.ProviderAccountSubjectDigest = ""
	store.current.GrantReceiptDigest = ""
	store.current.RevokedAt = &revokedAt
	store.current.Revision++
	store.current.UpdatedAt = input.OccurredAt
	return connectionmodel.MutationResult{Connection: store.current}, nil
}

func TestConnectionExposesGrantStateButNeverCredentialMaterial(t *testing.T) {
	now := time.Date(2026, time.August, 2, 9, 0, 0, 0, time.UTC)
	store := &connectionStore{}
	facade := connectionapp.NewCommandFacade(
		store,
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
			Capabilities: []string{"calendar.event.create"},
		}},
		grantVerifier{grant: connectionmodel.VerifiedGrant{
			AuthorizationID:              "authorization-1",
			CredentialRef:                "protected://calendar/account-1",
			ProviderAccountSubjectDigest: "sha256:" + strings.Repeat("a", 64),
			ReceiptDigest:                "sha256:" + strings.Repeat("c", 64),
			GrantedCapabilities:          []string{"calendar.event.create"},
		}},
		func() time.Time { return now },
	)
	result, err := facade.Create(context.Background(), connectionmodel.CreateInput{
		AccountID: "account-1", ConnectorID: "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       "native-receipt-1", IdempotencyKey: "command-1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if !result.Connection.IsActive(now) || !result.Connection.Grants("calendar.event.create") {
		t.Fatalf("active grant not reflected: %#v", result.Connection)
	}
	if result.Connection.ProviderAccountSubjectDigest != "sha256:"+strings.Repeat("a", 64) {
		t.Fatalf("verified provider account subject was not preserved internally")
	}
	queries := connectionapp.NewQueryFacade(store)
	readback, err := queries.Get(context.Background(), "account-1", "connection-1")
	if err != nil || readback.ConnectionID != result.Connection.ConnectionID {
		t.Fatalf("connection readback failed: connection=%+v err=%v", readback, err)
	}
	listed, err := queries.List(context.Background(), "account-1", 10)
	if err != nil || len(listed) != 1 || listed[0].ConnectionID != result.Connection.ConnectionID {
		t.Fatalf("connection list failed: connections=%+v err=%v", listed, err)
	}
	encoded, err := json.Marshal(result.Connection)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{
		"protected://",
		"sha256:" + strings.Repeat("a", 64),
		"grantReceiptDigest",
		"account-1",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("connection leaked protected material %q: %s", forbidden, encoded)
		}
	}
	revoked, err := facade.Revoke(context.Background(), connectionmodel.RevokeInput{
		AccountID:        "account-1",
		ConnectionID:     "connection-1",
		ExpectedRevision: 1,
		IdempotencyKey:   "revoke-1",
	})
	if err != nil || revoked.Connection.Status != connectionmodel.StatusRevoked ||
		revoked.Connection.Revision != 2 || revoked.Connection.CredentialRef != "" {
		t.Fatalf("connection revoke failed: result=%+v err=%v", revoked, err)
	}
}

func TestOAuthConnectionRequiresVerifiedProviderAccountSubjectDigest(t *testing.T) {
	now := time.Date(2026, time.August, 2, 9, 30, 0, 0, time.UTC)
	facade := connectionapp.NewCommandFacade(
		&connectionStore{},
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:       "google_calendar",
			Capabilities:      []string{"calendar.event.create"},
			AuthorizationMode: definitionmodel.AuthorizationOAuth2,
			Status:            definitionmodel.StatusActive,
		}},
		grantVerifier{grant: connectionmodel.VerifiedGrant{
			AuthorizationID:     "authorization-oauth-1",
			CredentialRef:       "protected://oauth/calendar/account-1",
			ReceiptDigest:       "sha256:" + strings.Repeat("c", 64),
			GrantedCapabilities: []string{"calendar.event.create"},
		}},
		func() time.Time { return now },
	)
	_, err := facade.Create(context.Background(), connectionmodel.CreateInput{
		AccountID:             "account-1",
		ConnectorID:           "google_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       "oauth-receipt-1",
		IdempotencyKey:        "connect-oauth-1",
	})
	if !errors.Is(err, connectionmodel.ErrGrantReceiptInvalid) {
		t.Fatalf("OAuth connection without subject digest error = %v", err)
	}
}

func TestConnectionRejectsCapabilityOutsideDefinition(t *testing.T) {
	facade := connectionapp.NewCommandFacade(
		&connectionStore{},
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID: "system_calendar", Status: definitionmodel.StatusActive,
			Capabilities: []string{"calendar.event.read"},
		}},
		grantVerifier{}, time.Now,
	)
	_, err := facade.Create(context.Background(), connectionmodel.CreateInput{
		AccountID: "account-1", ConnectorID: "system_calendar",
		RequestedCapabilities: []string{"calendar.event.create"},
		GrantReceiptRef:       "native-receipt-1", IdempotencyKey: "command-2",
	})
	if !errors.Is(err, connectionmodel.ErrCapabilityDenied) {
		t.Fatalf("want capability denied, got %v", err)
	}
}

type capabilityConnectionReader struct {
	connection connectionmodel.Connection
}

type connectorGrantStore struct {
	grants []grantmodel.ResolvedCapabilityGrant
}

func (store *connectorGrantStore) Save(
	_ context.Context,
	grant grantmodel.ResolvedCapabilityGrant,
) error {
	store.grants = append(store.grants, grant)
	return nil
}

func (store *connectorGrantStore) Load(
	_ context.Context,
	resolutionID string,
) (grantapp.StoredSession, error) {
	for _, grant := range store.grants {
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

func newConnectorCapabilityFacade(
	reader capabilityConnectionReader,
	definition definitionmodel.Definition,
	now time.Time,
) (*connectionapp.QueryFacade, *connectorGrantStore) {
	unavailable := grantcandidate.NewUnavailableSources("not required by connector resolution")
	resolver := grantresolver.NewCandidateResolver(
		unavailable,
		grantcandidate.NewConnectorReaderSource(
			reader,
			definitionReader{definition: definition},
			func() time.Time { return now },
		),
		unavailable,
		unavailable,
		func() time.Time { return now },
	)
	store := &connectorGrantStore{}
	session := grantapp.NewCapabilityGrantSessionFacade(resolver, store)
	return connectionapp.NewCapabilityQueryFacade(
		reader,
		grantadapter.NewMiddleware(session),
	), store
}

func connectorGrantAuthorization(t *testing.T) grantapp.TrustedRuntimeAuthorization {
	t.Helper()
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	return authorization
}

func (reader capabilityConnectionReader) Get(
	_ context.Context,
	accountID string,
	connectionID string,
) (connectionmodel.Connection, error) {
	if reader.connection.AccountID != accountID || reader.connection.ConnectionID != connectionID {
		return connectionmodel.Connection{}, connectionmodel.ErrNotFound
	}
	return reader.connection, nil
}

func (reader capabilityConnectionReader) List(
	context.Context,
	string,
	int,
) ([]connectionmodel.Connection, error) {
	return []connectionmodel.Connection{reader.connection}, nil
}

func TestCapabilityResolutionRechecksConnectionDefinitionAndSurface(t *testing.T) {
	now := time.Date(2026, time.August, 3, 15, 0, 0, 0, time.UTC)
	connection := connectionmodel.Connection{
		ConnectionID:        "connection-1",
		AccountID:           "account-1",
		ConnectorID:         "system_calendar",
		GrantedCapabilities: []string{"calendar.event.create"},
		Status:              connectionmodel.StatusActive,
		FreshnessAt:         now.Add(-time.Minute),
		Revision:            1,
		CreatedAt:           now.Add(-time.Hour),
		UpdatedAt:           now.Add(-time.Minute),
	}
	facade, store := newConnectorCapabilityFacade(
		capabilityConnectionReader{connection: connection},
		definitionmodel.Definition{
			ConnectorID:           "system_calendar",
			Capabilities:          []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"},
			Status:                definitionmodel.StatusActive,
			ReleaseDigest:         "sha256:" + strings.Repeat("a", 64),
		},
		now,
	)
	allowed, err := facade.ResolveCapability(context.Background(), connectorGrantAuthorization(t), connectionmodel.ResolveCapabilityInput{
		ResolutionID:   "resolution-allowed",
		CapabilityKey:  "calendar.event.create",
		SurfaceKind:    "personal",
		ConnectionRefs: []string{"connection-1"},
	})
	if err != nil || !allowed.Allowed || allowed.ConnectionID != "connection-1" ||
		allowed.Reason != connectionmodel.CapabilityReasonAllowed {
		t.Fatalf("active personal grant was not allowed: decision=%+v err=%v", allowed, err)
	}
	shared, err := facade.ResolveCapability(context.Background(), connectorGrantAuthorization(t), connectionmodel.ResolveCapabilityInput{
		ResolutionID:   "resolution-shared",
		CapabilityKey:  "calendar.event.create",
		SurfaceKind:    "circle",
		ConnectionRefs: []string{"connection-1"},
	})
	if err != nil || shared.Allowed || shared.Reason != connectionmodel.CapabilityReasonSurfaceDenied {
		t.Fatalf("personal connector leaked into shared surface: decision=%+v err=%v", shared, err)
	}
	if len(store.grants) != 1 {
		t.Fatalf("persisted capability sessions=%d want=1", len(store.grants))
	}
	connection.Status = connectionmodel.StatusRevoked
	revokedFacade, _ := newConnectorCapabilityFacade(
		capabilityConnectionReader{connection: connection},
		definitionmodel.Definition{
			ConnectorID:           "system_calendar",
			Capabilities:          []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"},
			Status:                definitionmodel.StatusActive,
			ReleaseDigest:         "sha256:" + strings.Repeat("a", 64),
		},
		now,
	)
	revoked, err := revokedFacade.ResolveCapability(context.Background(), connectorGrantAuthorization(t), connectionmodel.ResolveCapabilityInput{
		ResolutionID:   "resolution-revoked",
		CapabilityKey:  "calendar.event.create",
		SurfaceKind:    "personal",
		ConnectionRefs: []string{"connection-1"},
	})
	if err != nil || revoked.Allowed || revoked.Reason != connectionmodel.CapabilityReasonConnectionInactive {
		t.Fatalf("revoked connection did not fail closed: decision=%+v err=%v", revoked, err)
	}
}

func TestCapabilityResolutionInternalHTTPReturnsOnlyRedactedDecision(t *testing.T) {
	now := time.Date(2026, time.August, 3, 15, 0, 0, 0, time.UTC)
	facade, _ := newConnectorCapabilityFacade(
		capabilityConnectionReader{connection: connectionmodel.Connection{
			ConnectionID: "connection-1", AccountID: "account-1",
			ConnectorID:         "system_calendar",
			GrantedCapabilities: []string{"calendar.event.create"},
			Status:              connectionmodel.StatusActive, FreshnessAt: now.Add(-time.Minute),
			Revision: 1, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
		}},
		definitionmodel.Definition{
			ConnectorID: "system_calendar", Capabilities: []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"}, Status: definitionmodel.StatusActive,
			ReleaseDigest: "sha256:" + strings.Repeat("a", 64),
		},
		now,
	)
	mux := http.NewServeMux()
	connectionhttp.NewHandler(nil, facade).RegisterRoutes(mux)
	body := []byte(`{"capabilityKey":"calendar.event.create","surfaceKind":"personal","connectionRefs":["connection-1"]}`)
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-capability-grants:resolve",
		bytes.NewReader(body),
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType:      rtauth.TokenTypeAccess,
			Subject:        "account-1",
			ServiceActorID: "assistant-service",
			Scope:          "integration.connector_grant.read",
			Roles:          []string{"service"},
		},
		Actor: operation.ActorContext{AccountID: "account-1"},
	}))
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var decision map[string]any
	if err := json.Unmarshal(response.Body.Bytes(), &decision); err != nil {
		t.Fatal(err)
	}
	if decision["allowed"] != true || decision["connectionId"] != "connection-1" {
		t.Fatalf("decision=%#v", decision)
	}
	encoded := response.Body.String()
	for _, forbidden := range []string{"credential", "token", "protected://"} {
		if strings.Contains(encoded, forbidden) {
			t.Fatalf("internal capability decision leaked %q: %s", forbidden, encoded)
		}
	}
	spoofed := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-capability-grants:resolve",
		bytes.NewReader([]byte(`{"accountId":"account-spoofed","capabilityKey":"calendar.event.create","surfaceKind":"personal","connectionRefs":["connection-1"]}`)),
	).WithContext(request.Context())
	spoofedResponse := httptest.NewRecorder()
	mux.ServeHTTP(spoofedResponse, spoofed)
	if spoofedResponse.Code != http.StatusBadRequest {
		t.Fatalf("body accountId was not rejected: status=%d body=%s", spoofedResponse.Code, spoofedResponse.Body.String())
	}
	legacyServiceRequest := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-capability-grants:resolve",
		bytes.NewReader(body),
	)
	legacyServiceRequest = legacyServiceRequest.WithContext(rtauth.WithPrincipal(
		legacyServiceRequest.Context(),
		rtauth.Principal{
			Claims: rtauth.Claims{
				TokenType: rtauth.TokenTypeAccess,
				Subject:   "service:assistant-service",
				Scope:     "integration.connector_grant.read",
				Roles:     []string{"service"},
			},
			Actor: operation.ActorContext{AccountID: "service:assistant-service"},
		},
	))
	legacyServiceResponse := httptest.NewRecorder()
	mux.ServeHTTP(legacyServiceResponse, legacyServiceRequest)
	if legacyServiceResponse.Code != http.StatusForbidden {
		t.Fatalf(
			"legacy service subject was accepted as account: status=%d body=%s",
			legacyServiceResponse.Code,
			legacyServiceResponse.Body.String(),
		)
	}
}
