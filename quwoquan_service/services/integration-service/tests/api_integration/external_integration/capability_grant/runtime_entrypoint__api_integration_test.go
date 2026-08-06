// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
// readiness_case: resolve-capability-grant-api
package capability_grant_test

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"testing"
	"time"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantcandidate "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/candidate"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

func TestRuntimeEntrypointBuildsRedactedConnectorCandidateAndResolves(t *testing.T) {
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
	requirement := grantmodel.Requirement{
		ResolutionID:    "resolution-calendar-1",
		AccountID:       "account-1",
		CapabilityKey:   "calendar.event.create",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingUserConnector},
		Write:           true,
		ConfirmationRef: "confirmation-1",
		PermitRef:       "permit-1",
		IdempotencyKey:  "calendar-create-1",
		InputDigest:     apiDigest("calendar-input"),
	}
	resolver := grantresolver.NewCandidateResolver(
		nil,
		grantcandidate.NewConnectorReaderSource(
			reader,
			func() time.Time { return now },
		),
		nil,
		nil,
		func() time.Time { return now },
	)
	resolved, err := grantapp.NewCapabilityGrantSessionFacade(resolver).
		Resolve(context.Background(), requirement)
	if err != nil {
		t.Fatal(err)
	}
	if resolved.BindingKind != grantmodel.BindingUserConnector ||
		resolved.UserConnector == nil ||
		resolved.UserConnector.ConnectionID != "connection-calendar-1" {
		t.Fatalf("resolved=%+v", resolved)
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
	_, err := grantapp.NewCapabilityGrantSessionFacade(resolver).Resolve(
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
	context.Context,
	string,
	string,
) (connectionmodel.Connection, error) {
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

func apiDigest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}
