// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
package capability_grant_test

import (
	"context"
	"errors"
	"testing"
	"time"

	grantadapter "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/adapters/inbound/runtime"
	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
)

func TestCapabilityGrantTransportBindsTrustedAccountBeforeResolution(t *testing.T) {
	now := time.Date(2026, time.August, 8, 6, 0, 0, 0, time.UTC)
	source := recordingUserConnectorSource{values: []grantmodel.UserConnectorConnection{{
		CapabilityKey:  "calendar.event.create",
		AccountID:      "account-1",
		ConnectionID:   "connection-1",
		ConnectorID:    "calendar",
		ContractDigest: digest("calendar-contract"),
		GrantedCapabilities: []string{
			"calendar.event.create",
		},
		GrantState:                   grantmodel.ConnectorGrantActive,
		ProviderAccountSubjectDigest: digest("provider-account"),
		FreshnessAt:                  now,
		Revision:                     1,
	}}}
	store := &recordingSessionStore{}
	transport := grantadapter.NewMiddleware(grantapp.NewCapabilityGrantSessionFacade(
		userConnectorOnlyResolver{source: &source, now: now},
		store,
	))
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	decision, err := transport.ResolveConnectorGrant(
		context.Background(),
		authorization,
		grantapp.ConnectorResolutionRequest{
			ResolutionID:   "resolution-1",
			CapabilityKey:  "calendar.event.create",
			SurfaceKind:    "personal",
			ConnectionRefs: []string{"connection-1"},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if !decision.Allowed || decision.ConnectionID != "connection-1" ||
		source.accountID != "account-1" || store.count() != 1 {
		t.Fatalf(
			"decision=%+v sourceAccountID=%q sessions=%d",
			decision,
			source.accountID,
			store.count(),
		)
	}
}

func TestCapabilityGrantTransportRejectsMissingOrServiceAccountAuthorization(t *testing.T) {
	now := time.Date(2026, time.August, 8, 6, 5, 0, 0, time.UTC)
	source := recordingUserConnectorSource{}
	transport := grantadapter.NewMiddleware(grantapp.NewCapabilityGrantSessionFacade(
		userConnectorOnlyResolver{source: &source, now: now},
		&recordingSessionStore{},
	))
	request := grantapp.ConnectorResolutionRequest{
		ResolutionID:   "resolution-2",
		CapabilityKey:  "calendar.event.read",
		SurfaceKind:    "personal",
		ConnectionRefs: []string{"connection-2"},
	}
	if _, err := transport.ResolveConnectorGrant(
		context.Background(),
		grantapp.TrustedRuntimeAuthorization{},
		request,
	); !errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid) {
		t.Fatalf("missing authorization error=%v", err)
	}
	if _, err := grantapp.NewTrustedRuntimeAuthorization(
		"service:assistant-service",
		"assistant-service",
	); !errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid) {
		t.Fatalf("service subject accepted as account: %v", err)
	}
	if _, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"",
	); !errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid) {
		t.Fatalf("missing service actor error=%v", err)
	}
	if _, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"other-service",
	); !errors.Is(err, grantapp.ErrRuntimeAuthorizationInvalid) {
		t.Fatalf("unlisted service actor accepted: %v", err)
	}
	if source.calls != 0 {
		t.Fatalf("candidate source called %d times before authority rejection", source.calls)
	}
}

func TestConnectorDenialNeverMasksSessionStoreFailure(t *testing.T) {
	now := time.Date(2026, time.August, 8, 6, 10, 0, 0, time.UTC)
	storeFailure := errors.New("redis write unavailable")
	source := recordingUserConnectorSource{values: []grantmodel.UserConnectorConnection{{
		CapabilityKey:                "calendar.event.read",
		AccountID:                    "account-1",
		ConnectionID:                 "connection-1",
		ConnectorID:                  "calendar",
		ContractDigest:               digest("calendar-contract"),
		GrantedCapabilities:          []string{"calendar.event.read"},
		GrantState:                   grantmodel.ConnectorGrantActive,
		ProviderAccountSubjectDigest: digest("provider-account"),
		FreshnessAt:                  now,
		Revision:                     1,
	}}}
	transport := grantadapter.NewMiddleware(grantapp.NewCapabilityGrantSessionFacade(
		userConnectorOnlyResolver{source: &source, now: now},
		&recordingSessionStore{err: storeFailure},
	))
	authorization, err := grantapp.NewTrustedRuntimeAuthorization(
		"account-1",
		"assistant-service",
	)
	if err != nil {
		t.Fatal(err)
	}
	decision, err := transport.ResolveConnectorGrant(
		context.Background(),
		authorization,
		grantapp.ConnectorResolutionRequest{
			ResolutionID:   "resolution-store-failure",
			CapabilityKey:  "calendar.event.read",
			SurfaceKind:    "personal",
			ConnectionRefs: []string{"connection-1"},
		},
	)
	if !errors.Is(err, grantapp.ErrCapabilityGrantSessionUnavailable) ||
		decision.Allowed {
		t.Fatalf("store failure was converted to denial: decision=%+v err=%v", decision, err)
	}
}

type userConnectorOnlyResolver struct {
	source *recordingUserConnectorSource
	now    time.Time
}

func (resolver userConnectorOnlyResolver) ResolveCapabilityGrant(
	ctx context.Context,
	requirement grantmodel.Requirement,
) (grantmodel.ResolvedCapabilityGrant, error) {
	values, err := resolver.source.ListCandidates(ctx, requirement)
	if err != nil {
		return grantmodel.ResolvedCapabilityGrant{}, err
	}
	return grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{UserConnectors: values},
		resolver.now,
	)
}

type recordingUserConnectorSource struct {
	values    []grantmodel.UserConnectorConnection
	accountID string
	calls     int
}

func (source *recordingUserConnectorSource) ListCandidates(
	_ context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.UserConnectorConnection, error) {
	source.calls++
	source.accountID = requirement.AccountID
	return append([]grantmodel.UserConnectorConnection(nil), source.values...), nil
}
