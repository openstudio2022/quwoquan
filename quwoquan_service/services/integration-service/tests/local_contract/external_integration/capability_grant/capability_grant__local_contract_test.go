// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
// readiness_case: resolve-capability-grant-local
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
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
	connectionmodel "quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

func TestPublicProviderUnavailableFailsClosedWithoutConnectorLifecycle(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 0, 0, 0, time.UTC)
	_, err := grantmodel.ResolveCapabilityGrant(
		grantmodel.Requirement{
			ResolutionID:    "resolution-weather-1",
			CapabilityKey:   "weather.forecast.read",
			BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
		},
		grantmodel.Candidates{PublicProviders: []grantmodel.PublicProviderBinding{{
			CapabilityKey: "weather.forecast.read",
			State:         grantmodel.ProviderBindingDisabled,
			ProbeState:    grantmodel.ProviderProbeNotRun,
		}}},
		now,
	)
	if !errors.Is(err, grantmodel.ErrProviderUnavailable) {
		t.Fatalf("provider unavailable error = %v", err)
	}
}

func TestCapabilityGrantSessionFacadeIsTheSoleTypedRuntimeEntryPoint(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 2, 0, 0, time.UTC)
	resolver := grantresolver.NewCandidateResolver(
		nil,
		nil,
		nil,
		domainOperationSourceFunc(func(
			context.Context,
			grantmodel.Requirement,
		) ([]grantapp.DomainOperationCandidate, error) {
			return []grantapp.DomainOperationCandidate{{
				CapabilityKey: "circle.gathering_plan.propose",
				Binding: grantmodel.DomainOperationBinding{
					OwnerOperationID: "circle.gathering_plan.ProposeGatheringPlan",
					ContractDigest:   digest("gathering-plan-proposal-contract"),
				},
			}}, nil
		}),
		func() time.Time { return now },
	)
	store := &recordingSessionStore{}
	facade := grantapp.NewCapabilityGrantSessionFacade(resolver, store)
	resolved, err := facade.Resolve(
		context.Background(),
		grantmodel.Requirement{
			ResolutionID:    "resolution-domain-operation-1",
			CapabilityKey:   "circle.gathering_plan.propose",
			BindingPriority: []grantmodel.BindingKind{grantmodel.BindingDomainOperation},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolved.BindingKind != grantmodel.BindingDomainOperation ||
		resolved.DomainOperation == nil || !resolved.ResolvedAt.Equal(now) {
		t.Fatalf("resolved=%+v", resolved)
	}
	if store.count() != 1 {
		t.Fatalf("persisted sessions=%d want=1", store.count())
	}
}

func TestPublicProviderRequiresReadyBindingAndPassedProbe(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 5, 0, 0, time.UTC)
	requirement := grantmodel.Requirement{
		ResolutionID:    "resolution-poi-1",
		CapabilityKey:   "location.poi.search",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
	}
	binding := grantmodel.PublicProviderBinding{
		CapabilityKey:  "location.poi.search",
		AdapterID:      "ext.map.nominatim",
		ContractDigest: digest("nominatim-contract"),
		ConfigRef:      "environment_binding:integration.location.poi",
		TimeoutMs:      1200,
		RatePolicyRef:  "config:integration.public_provider.poi",
		State:          grantmodel.ProviderBindingReady,
		ProbeState:     grantmodel.ProviderProbeFailed,
	}

	_, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{PublicProviders: []grantmodel.PublicProviderBinding{binding}},
		now,
	)
	if !errors.Is(err, grantmodel.ErrProviderUnavailable) {
		t.Fatalf("failed probe error = %v", err)
	}

	binding.ProbeState = grantmodel.ProviderProbePassed
	resolved, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{PublicProviders: []grantmodel.PublicProviderBinding{binding}},
		now,
	)
	if err != nil || resolved.BindingKind != grantmodel.BindingPublicProvider ||
		resolved.PublicProvider == nil ||
		resolved.PublicProvider.ConfigRef != binding.ConfigRef {
		t.Fatalf("ready public provider result=%+v err=%v", resolved, err)
	}
}

func TestPublicProviderFailsClosedOutsideConfiguredRegion(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 7, 0, 0, time.UTC)
	requirement := grantmodel.Requirement{
		ResolutionID:    "resolution-weather-region-1",
		CapabilityKey:   "weather.forecast.read",
		RegionCode:      "cn",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
	}
	binding := grantmodel.PublicProviderBinding{
		CapabilityKey:        "weather.forecast.read",
		SupportedRegionCodes: []string{"jp"},
		AdapterID:            "ext.weather.open_meteo",
		ContractDigest:       digest("open-meteo-contract"),
		ConfigRef:            "environment_binding:assistant.weather.forecast",
		TimeoutMs:            1200,
		RatePolicyRef:        "config:assistant.weather.forecast",
		State:                grantmodel.ProviderBindingReady,
		ProbeState:           grantmodel.ProviderProbePassed,
	}

	_, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{
			PublicProviders: []grantmodel.PublicProviderBinding{binding},
		},
		now,
	)
	if !errors.Is(err, grantmodel.ErrProviderUnavailable) {
		t.Fatalf("region mismatch error=%v, want provider unavailable", err)
	}

	binding.SupportedRegionCodes = []string{" CN ", "cn"}
	resolved, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{
			PublicProviders: []grantmodel.PublicProviderBinding{binding},
		},
		now,
	)
	if err != nil || resolved.PublicProvider == nil ||
		len(resolved.PublicProvider.SupportedRegionCodes) != 1 ||
		resolved.PublicProvider.SupportedRegionCodes[0] != "CN" {
		t.Fatalf("region-compatible provider result=%+v err=%v", resolved, err)
	}
}

func TestOAuthRevocationIsNotParsedAsAnActiveUserConnectorGrant(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 10, 0, 0, time.UTC)
	revokedAt := now.Add(-time.Minute)
	connector, err := grantapp.ParseUserConnectorConnection(
		"account-1",
		"calendar.event.create",
		connectionmodel.Connection{
			ConnectionID:        "connection-1",
			AccountID:           "account-1",
			ConnectorID:         "google_calendar",
			GrantedCapabilities: []string{"calendar.event.create"},
			Status:              connectionmodel.StatusRevoked,
			RevokedAt:           &revokedAt,
			FreshnessAt:         now.Add(-time.Hour),
			Revision:            2,
		},
		now,
	)
	if err != nil {
		t.Fatal(err)
	}
	_, err = grantmodel.ResolveCapabilityGrant(
		grantmodel.Requirement{
			ResolutionID:    "resolution-calendar-1",
			AccountID:       "account-1",
			CapabilityKey:   "calendar.event.create",
			BindingPriority: []grantmodel.BindingKind{grantmodel.BindingUserConnector},
			Write:           true,
			ConfirmationRef: "confirmation-1",
			PermitRef:       "permit-1",
			IdempotencyKey:  "calendar-create-1",
			InputDigest:     digest("calendar-input"),
		},
		grantmodel.Candidates{UserConnectors: []grantmodel.UserConnectorConnection{connector}},
		now,
	)
	if !errors.Is(err, grantmodel.ErrConnectorRevoked) {
		t.Fatalf("OAuth revoked error = %v", err)
	}
}

func TestDeviceUnavailableAndPermissionDeniedAreDistinctStructuredFailures(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 20, 0, 0, time.UTC)
	requirement := grantmodel.Requirement{
		ResolutionID:    "resolution-device-1",
		AccountID:       "account-1",
		CapabilityKey:   "calendar.event.update",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingDevice},
		Write:           true,
		ConfirmationRef: "confirmation-1",
		PermitRef:       "permit-1",
		IdempotencyKey:  "calendar-update-1",
		InputDigest:     digest("calendar-update-input"),
	}
	unavailable := grantmodel.DeviceCapabilityBinding{
		CapabilityKey: "calendar.event.update",
		Availability:  grantmodel.DeviceUnavailable,
		Permission:    grantmodel.DevicePermissionGranted,
	}
	_, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{DeviceBindings: []grantmodel.DeviceCapabilityBinding{unavailable}},
		now,
	)
	if !errors.Is(err, grantmodel.ErrDeviceUnavailable) {
		t.Fatalf("device unavailable error = %v", err)
	}

	denied := unavailable
	denied.Availability = grantmodel.DeviceAvailable
	denied.Permission = grantmodel.DevicePermissionDenied
	denied.BridgeCapability = "calendarWrite"
	denied.AttestationDigest = digest("device-attestation")
	_, err = grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{DeviceBindings: []grantmodel.DeviceCapabilityBinding{denied}},
		now,
	)
	if !errors.Is(err, grantmodel.ErrDevicePermissionDenied) {
		t.Fatalf("device permission denied error = %v", err)
	}
}

func TestResolutionPrioritySelectsDeviceAndNeverFallsBackAfterDenial(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 30, 0, 0, time.UTC)
	requirement := grantmodel.Requirement{
		ResolutionID:  "resolution-priority-1",
		AccountID:     "account-1",
		CapabilityKey: "calendar.event.delete",
		BindingPriority: []grantmodel.BindingKind{
			grantmodel.BindingDevice,
			grantmodel.BindingUserConnector,
		},
		Write:           true,
		ConfirmationRef: "confirmation-1",
		PermitRef:       "permit-1",
		IdempotencyKey:  "calendar-delete-1",
		InputDigest:     digest("calendar-delete-input"),
	}
	device := grantmodel.DeviceCapabilityBinding{
		CapabilityKey:     "calendar.event.delete",
		BridgeCapability:  "calendarWrite",
		Availability:      grantmodel.DeviceAvailable,
		Permission:        grantmodel.DevicePermissionGranted,
		AttestationDigest: digest("device-attestation"),
	}
	connector := grantmodel.UserConnectorConnection{
		CapabilityKey:                "calendar.event.delete",
		AccountID:                    "account-1",
		ConnectionID:                 "connection-1",
		ConnectorID:                  "google_calendar",
		ContractDigest:               digest("google-calendar-contract"),
		GrantedCapabilities:          []string{"calendar.event.delete"},
		GrantState:                   grantmodel.ConnectorGrantActive,
		ProviderAccountSubjectDigest: digest("provider-account-subject"),
		Revision:                     1,
	}
	resolved, err := grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{
			DeviceBindings: []grantmodel.DeviceCapabilityBinding{device},
			UserConnectors: []grantmodel.UserConnectorConnection{connector},
		},
		now,
	)
	if err != nil || resolved.BindingKind != grantmodel.BindingDevice ||
		resolved.DeviceBinding == nil || resolved.UserConnector != nil {
		t.Fatalf("unexpected priority result: grant=%+v err=%v", resolved, err)
	}

	resolved, err = grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{
			UserConnectors: []grantmodel.UserConnectorConnection{connector},
		},
		now,
	)
	if err != nil || resolved.BindingKind != grantmodel.BindingUserConnector ||
		resolved.UserConnector == nil || resolved.DeviceBinding != nil {
		t.Fatalf("authorized connector result: grant=%+v err=%v", resolved, err)
	}

	device.Permission = grantmodel.DevicePermissionDenied
	_, err = grantmodel.ResolveCapabilityGrant(
		requirement,
		grantmodel.Candidates{
			DeviceBindings: []grantmodel.DeviceCapabilityBinding{device},
			UserConnectors: []grantmodel.UserConnectorConnection{connector},
		},
		now,
	)
	if !errors.Is(err, grantmodel.ErrDevicePermissionDenied) {
		t.Fatalf("denied device must not fall back to connector: %v", err)
	}
}

func TestCalendarWritesRequireConfirmationPermitAndIdempotency(t *testing.T) {
	now := time.Date(2026, time.August, 6, 5, 40, 0, 0, time.UTC)
	base := grantmodel.Requirement{
		ResolutionID:    "resolution-write-1",
		CapabilityKey:   "calendar.event.create",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingDomainOperation},
		Write:           true,
		ConfirmationRef: "confirmation-1",
		PermitRef:       "permit-1",
		IdempotencyKey:  "calendar-create-1",
		InputDigest:     digest("calendar-input"),
	}
	candidates := grantmodel.Candidates{DomainOperations: []grantmodel.DomainOperationBinding{{
		OwnerOperationID: "calendar.CreateEvent",
		ContractDigest:   digest("calendar-contract"),
	}}}

	assertMissing := func(name string, mutate func(*grantmodel.Requirement), expected error) {
		t.Helper()
		requirement := base
		mutate(&requirement)
		_, err := grantmodel.ResolveCapabilityGrant(requirement, candidates, now)
		if !errors.Is(err, expected) {
			t.Fatalf("%s error = %v", name, err)
		}
	}
	assertMissing("confirmation", func(value *grantmodel.Requirement) {
		value.ConfirmationRef = ""
	}, grantmodel.ErrConfirmationRequired)
	assertMissing("permit", func(value *grantmodel.Requirement) {
		value.PermitRef = ""
	}, grantmodel.ErrPermitRequired)
	assertMissing("idempotency", func(value *grantmodel.Requirement) {
		value.IdempotencyKey = ""
	}, grantmodel.ErrIdempotencyRequired)

	resolved, err := grantmodel.ResolveCapabilityGrant(base, candidates, now)
	if err != nil || resolved.DomainOperation == nil ||
		resolved.DomainOperation.OwnerOperationID != "calendar.CreateEvent" ||
		resolved.DomainOperation.ContractDigest != digest("calendar-contract") {
		t.Fatalf("domain operation result=%+v err=%v", resolved, err)
	}
}

func digest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}
