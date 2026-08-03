// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
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

type connectionStore struct{ created connectionmodel.CreateCommand }

func (*connectionStore) Replay(
	context.Context,
	string,
	string,
	string,
	string,
) (connectionmodel.MutationResult, bool, error) {
	return connectionmodel.MutationResult{}, false, nil
}

func (store *connectionStore) Get(context.Context, string, string) (connectionmodel.Connection, error) {
	return connectionmodel.Connection{}, connectionmodel.ErrNotFound
}

func (store *connectionStore) List(context.Context, string, int) ([]connectionmodel.Connection, error) {
	return nil, nil
}

func (store *connectionStore) Create(_ context.Context, command connectionmodel.CreateCommand) (connectionmodel.MutationResult, error) {
	store.created = command
	return connectionmodel.MutationResult{Connection: connectionmodel.Connection{
		ConnectionID: "connection-1", AccountID: command.AccountID,
		ConnectorID: command.ConnectorID, GrantedCapabilities: command.GrantedCapabilities,
		Status: connectionmodel.StatusActive, CredentialRef: command.CredentialRef,
		GrantReceiptDigest: command.GrantReceiptDigest, FreshnessAt: command.OccurredAt,
		Revision: 1, CreatedAt: command.OccurredAt, UpdatedAt: command.OccurredAt,
	}}, nil
}

func (store *connectionStore) Revoke(context.Context, connectionmodel.RevokeInput) (connectionmodel.MutationResult, error) {
	return connectionmodel.MutationResult{}, nil
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
			AuthorizationID:     "authorization-1",
			CredentialRef:       "protected://calendar/account-1",
			ReceiptDigest:       "sha256:" + strings.Repeat("c", 64),
			GrantedCapabilities: []string{"calendar.event.create"},
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
	encoded, err := json.Marshal(result.Connection)
	if err != nil {
		t.Fatal(err)
	}
	for _, forbidden := range []string{"protected://", "grantReceiptDigest", "account-1"} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("connection leaked protected material %q: %s", forbidden, encoded)
		}
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
	facade := connectionapp.NewCapabilityQueryFacade(
		capabilityConnectionReader{connection: connection},
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:           "system_calendar",
			Capabilities:          []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"},
			Status:                definitionmodel.StatusActive,
		}},
		func() time.Time { return now },
	)
	allowed, err := facade.ResolveCapability(context.Background(), connectionmodel.ResolveCapabilityInput{
		AccountID:      "account-1",
		CapabilityKey:  "calendar.event.create",
		SurfaceKind:    "personal",
		ConnectionRefs: []string{"connection-1"},
	})
	if err != nil || !allowed.Allowed || allowed.ConnectionID != "connection-1" ||
		allowed.Reason != connectionmodel.CapabilityReasonAllowed {
		t.Fatalf("active personal grant was not allowed: decision=%+v err=%v", allowed, err)
	}
	shared, err := facade.ResolveCapability(context.Background(), connectionmodel.ResolveCapabilityInput{
		AccountID:      "account-1",
		CapabilityKey:  "calendar.event.create",
		SurfaceKind:    "circle",
		ConnectionRefs: []string{"connection-1"},
	})
	if err != nil || shared.Allowed || shared.Reason != connectionmodel.CapabilityReasonSurfaceDenied {
		t.Fatalf("personal connector leaked into shared surface: decision=%+v err=%v", shared, err)
	}
	connection.Status = connectionmodel.StatusRevoked
	revokedFacade := connectionapp.NewCapabilityQueryFacade(
		capabilityConnectionReader{connection: connection},
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID:           "system_calendar",
			Capabilities:          []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"},
			Status:                definitionmodel.StatusActive,
		}},
		func() time.Time { return now },
	)
	revoked, err := revokedFacade.ResolveCapability(context.Background(), connectionmodel.ResolveCapabilityInput{
		AccountID:      "account-1",
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
	facade := connectionapp.NewCapabilityQueryFacade(
		capabilityConnectionReader{connection: connectionmodel.Connection{
			ConnectionID: "connection-1", AccountID: "account-1",
			ConnectorID:         "system_calendar",
			GrantedCapabilities: []string{"calendar.event.create"},
			Status:              connectionmodel.StatusActive, FreshnessAt: now.Add(-time.Minute),
			Revision: 1, CreatedAt: now.Add(-time.Hour), UpdatedAt: now.Add(-time.Minute),
		}},
		definitionReader{definition: definitionmodel.Definition{
			ConnectorID: "system_calendar", Capabilities: []string{"calendar.event.create"},
			SupportedSurfaceKinds: []string{"personal"}, Status: definitionmodel.StatusActive,
		}},
		func() time.Time { return now },
	)
	mux := http.NewServeMux()
	connectionhttp.NewHandler(nil, facade).RegisterRoutes(mux)
	body := []byte(`{"accountId":"account-1","capabilityKey":"calendar.event.create","surfaceKind":"personal","connectionRefs":["connection-1"]}`)
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/integrations/connector-capability-grants:resolve",
		bytes.NewReader(body),
	)
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
}
