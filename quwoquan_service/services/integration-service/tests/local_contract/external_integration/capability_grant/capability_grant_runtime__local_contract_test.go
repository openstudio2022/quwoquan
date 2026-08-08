// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-003
package capability_grant_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	grantapp "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/application"
	grantmodel "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/domain/model"
	grantresolver "quwoquan_service/services/integration-service/internal/external_integration/capability_grant/infrastructure/resolver"
)

func TestCapabilityGrantOwnsOneTypedNonHTTPRuntimeEntrypoint(t *testing.T) {
	data, err := os.ReadFile(filepath.Join(
		integrationServiceRoot(t),
		"contracts",
		"external_integration",
		"capability_grant",
		"operations.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	var document struct {
		APIRoutes          []any `yaml:"api_routes"`
		RuntimeEntrypoints []struct {
			Name        string `yaml:"name"`
			RuntimeKind string `yaml:"kind"`
			Phase       string `yaml:"phase"`
			Application struct {
				Kind        string `yaml:"kind"`
				Facet       string `yaml:"facet"`
				Method      string `yaml:"method"`
				ObjectOwner string `yaml:"object_owner"`
			} `yaml:"application"`
		} `yaml:"runtime_entrypoints"`
	}
	if err := yaml.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	if len(document.APIRoutes) != 0 {
		t.Fatalf("capability grant must not expose HTTP routes: %+v", document.APIRoutes)
	}
	if len(document.RuntimeEntrypoints) != 1 {
		t.Fatalf("runtime entrypoints=%d, want one", len(document.RuntimeEntrypoints))
	}
	entrypoint := document.RuntimeEntrypoints[0]
	if entrypoint.Name != "ResolveCapabilityGrant" ||
		entrypoint.RuntimeKind != "middleware" ||
		entrypoint.Phase != "post_authorization_pre_owner_proxy" ||
		entrypoint.Application.Kind != "session" ||
		entrypoint.Application.Facet != "CapabilityGrantSessionFacade" ||
		entrypoint.Application.Method != "resolve" ||
		entrypoint.Application.ObjectOwner != "CapabilityGrant" {
		t.Fatalf("runtime entrypoint drifted: %+v", entrypoint)
	}
}

func TestCandidateResolverFailsClosedWithoutLowerPriorityFallback(t *testing.T) {
	now := time.Date(2026, time.August, 6, 6, 0, 0, 0, time.UTC)
	connectorCalls := 0
	resolver := grantresolver.NewCandidateResolver(
		publicProviderSourceFunc(func(
			context.Context,
			grantmodel.Requirement,
		) ([]grantmodel.PublicProviderBinding, error) {
			return []grantmodel.PublicProviderBinding{{
				CapabilityKey: "weather.forecast.read",
				State:         grantmodel.ProviderBindingUnavailable,
				ProbeState:    grantmodel.ProviderProbeFailed,
			}}, nil
		}),
		userConnectorSourceFunc(func(
			context.Context,
			grantmodel.Requirement,
		) ([]grantmodel.UserConnectorConnection, error) {
			connectorCalls++
			return nil, nil
		}),
		nil,
		nil,
		func() time.Time { return now },
	)
	facade := grantapp.NewCapabilityGrantSessionFacade(
		resolver,
		&recordingSessionStore{},
	)
	_, err := facade.Resolve(context.Background(), grantmodel.Requirement{
		ResolutionID:  "resolution-provider-unavailable",
		AccountID:     "account-1",
		CapabilityKey: "weather.forecast.read",
		BindingPriority: []grantmodel.BindingKind{
			grantmodel.BindingPublicProvider,
			grantmodel.BindingUserConnector,
		},
	})
	if !errors.Is(err, grantmodel.ErrProviderUnavailable) {
		t.Fatalf("provider unavailable error=%v", err)
	}
	if connectorCalls != 0 {
		t.Fatalf("lower-priority connector source called %d times", connectorCalls)
	}
}

func TestCandidateResolverPreservesRevokedAndDeviceDeniedFailures(t *testing.T) {
	now := time.Date(2026, time.August, 6, 6, 5, 0, 0, time.UTC)
	t.Run("revoked connector", func(t *testing.T) {
		resolver := grantresolver.NewCandidateResolver(
			nil,
			userConnectorSourceFunc(func(
				context.Context,
				grantmodel.Requirement,
			) ([]grantmodel.UserConnectorConnection, error) {
				return []grantmodel.UserConnectorConnection{{
					CapabilityKey:                "calendar.event.create",
					AccountID:                    "account-1",
					ConnectionID:                 "connection-1",
					ConnectorID:                  "calendar",
					ContractDigest:               digest("calendar-contract"),
					GrantedCapabilities:          []string{"calendar.event.create"},
					GrantState:                   grantmodel.ConnectorGrantRevoked,
					ProviderAccountSubjectDigest: digest("subject"),
					FreshnessAt:                  now,
					Revision:                     2,
				}}, nil
			}),
			nil,
			nil,
			func() time.Time { return now },
		)
		_, err := resolver.ResolveCapabilityGrant(
			context.Background(),
			writeRequirement("resolution-revoked"),
		)
		if !errors.Is(err, grantmodel.ErrConnectorRevoked) {
			t.Fatalf("revoked connector error=%v", err)
		}
	})

	t.Run("device permission denied", func(t *testing.T) {
		requirement := writeRequirement("resolution-device-denied")
		requirement.BindingPriority = []grantmodel.BindingKind{grantmodel.BindingDevice}
		resolver := grantresolver.NewCandidateResolver(
			nil,
			nil,
			deviceCapabilitySourceFunc(func(
				context.Context,
				grantmodel.Requirement,
			) ([]grantmodel.DeviceCapabilityBinding, error) {
				return []grantmodel.DeviceCapabilityBinding{{
					CapabilityKey:     requirement.CapabilityKey,
					BridgeCapability:  "calendarWrite",
					Availability:      grantmodel.DeviceAvailable,
					Permission:        grantmodel.DevicePermissionDenied,
					AttestationDigest: digest("device"),
				}}, nil
			}),
			nil,
			func() time.Time { return now },
		)
		_, err := resolver.ResolveCapabilityGrant(context.Background(), requirement)
		if !errors.Is(err, grantmodel.ErrDevicePermissionDenied) {
			t.Fatalf("device denied error=%v", err)
		}
	})
}

func TestCandidateResolverRejectsSourceUnavailableAndDomainMismatch(t *testing.T) {
	now := time.Date(2026, time.August, 6, 6, 10, 0, 0, time.UTC)
	t.Run("source unavailable", func(t *testing.T) {
		resolver := grantresolver.NewCandidateResolver(
			publicProviderSourceFunc(func(
				context.Context,
				grantmodel.Requirement,
			) ([]grantmodel.PublicProviderBinding, error) {
				return nil, errors.New("provider registry unavailable")
			}),
			nil,
			nil,
			nil,
			func() time.Time { return now },
		)
		_, err := resolver.ResolveCapabilityGrant(
			context.Background(),
			grantmodel.Requirement{
				ResolutionID:    "resolution-source-unavailable",
				CapabilityKey:   "weather.forecast.read",
				BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
			},
		)
		if !errors.Is(err, grantapp.ErrCandidateSourceUnavailable) {
			t.Fatalf("source unavailable error=%v", err)
		}
	})

	t.Run("domain mismatch", func(t *testing.T) {
		resolver := grantresolver.NewCandidateResolver(
			nil,
			nil,
			nil,
			domainOperationSourceFunc(func(
				context.Context,
				grantmodel.Requirement,
			) ([]grantapp.DomainOperationCandidate, error) {
				return []grantapp.DomainOperationCandidate{{
					CapabilityKey: "calendar.event.delete",
					Binding: grantmodel.DomainOperationBinding{
						OwnerOperationID: "calendar.CreateEvent",
						ContractDigest:   digest("calendar-owner"),
					},
				}}, nil
			}),
			func() time.Time { return now },
		)
		requirement := writeRequirement("resolution-domain-mismatch")
		requirement.BindingPriority = []grantmodel.BindingKind{
			grantmodel.BindingDomainOperation,
		}
		_, err := resolver.ResolveCapabilityGrant(context.Background(), requirement)
		if !errors.Is(err, grantapp.ErrCandidateDomainMismatch) {
			t.Fatalf("domain mismatch error=%v", err)
		}
	})
}

func TestCandidateResolverNormalizesTypedSourceOutput(t *testing.T) {
	now := time.Date(2026, time.August, 6, 6, 15, 0, 0, time.UTC)
	resolver := grantresolver.NewCandidateResolver(
		publicProviderSourceFunc(func(
			context.Context,
			grantmodel.Requirement,
		) ([]grantmodel.PublicProviderBinding, error) {
			return []grantmodel.PublicProviderBinding{{
				CapabilityKey:  " weather.forecast.read ",
				AdapterID:      " provider.weather ",
				ContractDigest: " " + digest("weather") + " ",
				ConfigRef:      " config:weather ",
				TimeoutMs:      800,
				RatePolicyRef:  " policy:weather ",
				State:          grantmodel.ProviderBindingState(" ready "),
				ProbeState:     grantmodel.ProviderProbeState(" passed "),
			}}, nil
		}),
		nil,
		nil,
		nil,
		func() time.Time { return now },
	)
	resolved, err := resolver.ResolveCapabilityGrant(
		context.Background(),
		grantmodel.Requirement{
			ResolutionID:    "resolution-normalized",
			CapabilityKey:   "weather.forecast.read",
			BindingPriority: []grantmodel.BindingKind{grantmodel.BindingPublicProvider},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolved.PublicProvider == nil ||
		resolved.PublicProvider.AdapterID != "provider.weather" ||
		resolved.PublicProvider.ConfigRef != "config:weather" ||
		resolved.PublicProvider.RatePolicyRef != "policy:weather" {
		t.Fatalf("source output was not normalized: %+v", resolved)
	}
}

func writeRequirement(resolutionID string) grantmodel.Requirement {
	return grantmodel.Requirement{
		ResolutionID:    resolutionID,
		AccountID:       "account-1",
		CapabilityKey:   "calendar.event.create",
		BindingPriority: []grantmodel.BindingKind{grantmodel.BindingUserConnector},
		Write:           true,
		ConfirmationRef: "confirmation-1",
		PermitRef:       "permit-1",
		IdempotencyKey:  "calendar-create-1",
		InputDigest:     digest("calendar-input"),
	}
}

func integrationServiceRoot(t *testing.T) string {
	t.Helper()
	_, sourcePath, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test source path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(sourcePath), "../../../.."))
}

type publicProviderSourceFunc func(
	context.Context,
	grantmodel.Requirement,
) ([]grantmodel.PublicProviderBinding, error)

func (source publicProviderSourceFunc) PublicProviderCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.PublicProviderBinding, error) {
	return source(ctx, requirement)
}

type userConnectorSourceFunc func(
	context.Context,
	grantmodel.Requirement,
) ([]grantmodel.UserConnectorConnection, error)

func (source userConnectorSourceFunc) UserConnectorCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.UserConnectorConnection, error) {
	return source(ctx, requirement)
}

type deviceCapabilitySourceFunc func(
	context.Context,
	grantmodel.Requirement,
) ([]grantmodel.DeviceCapabilityBinding, error)

func (source deviceCapabilitySourceFunc) DeviceCapabilityCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantmodel.DeviceCapabilityBinding, error) {
	return source(ctx, requirement)
}

type domainOperationSourceFunc func(
	context.Context,
	grantmodel.Requirement,
) ([]grantapp.DomainOperationCandidate, error)

func (source domainOperationSourceFunc) DomainOperationCandidates(
	ctx context.Context,
	requirement grantmodel.Requirement,
) ([]grantapp.DomainOperationCandidate, error) {
	return source(ctx, requirement)
}
