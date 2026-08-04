// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-002
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

type contextResolverFunc func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error)

func (f contextResolverFunc) Resolve(
	_ context.Context,
	request skillcontext.ResolveRequest,
) (skillcontext.ResolvedContext, error) {
	return f(request)
}

func contextReaderDescriptor(
	resolverRef string,
	sourceKind string,
	authority generated.AssistantContextAuthority,
	sensitivity generated.AssistantContextSensitivity,
) readermodel.Descriptor {
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID:        "test." + resolverRef,
		ResolverRef:         resolverRef,
		OwnerService:        "test-service",
		OwnerOperationRefs:  []string{"test.reader.Resolve"},
		InputSchemaRef:      "test.ResolveQuery",
		OutputSchemaRef:     "test.ContextSegment",
		AcceptedSourceKinds: []string{sourceKind},
		Authority:           authority,
		Sensitivity:         sensitivity,
		SurfaceKinds: []readermodel.SurfaceKind{
			readermodel.SurfacePersonal,
			readermodel.SurfaceShared,
			readermodel.SurfacePublic,
		},
		ArtifactPolicy: readermodel.ArtifactInlineOrStored,
		CitationPolicy: readermodel.CitationSourceReference,
	})
	if err != nil {
		panic(err)
	}
	return descriptor
}

type contextReaderBinding struct {
	descriptor readermodel.Descriptor
	resolver   skillcontext.Resolver
}

func contextReaderRegistry(
	t *testing.T,
	bindings ...contextReaderBinding,
) *skillcontext.ResolverRegistry {
	t.Helper()
	descriptors := make([]readermodel.Descriptor, 0, len(bindings))
	resolvers := make([]skillcontext.RegisteredResolver, 0, len(bindings))
	for _, binding := range bindings {
		descriptors = append(descriptors, binding.descriptor)
		resolvers = append(resolvers, skillcontext.RegisteredResolver{
			ResolverRef: binding.descriptor.ResolverRef,
			Resolver:    binding.resolver,
		})
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	registry, err := skillcontext.NewResolverRegistry(catalog, resolvers...)
	if err != nil {
		t.Fatal(err)
	}
	return registry
}

func TestSkillContextLoadsOnlySelectedProfileResolversAndArtifactsLargeValues(t *testing.T) {
	now := time.Now().UTC()
	pageCalls := 0
	unusedCalls := 0
	registry := contextReaderRegistry(
		t,
		contextReaderBinding{descriptor: contextReaderDescriptor(
			"page.current", "page",
			generated.AssistantContextAuthorityDeviceObserved,
			generated.AssistantContextSensitivityInternal,
		), resolver: contextResolverFunc(func(
			request skillcontext.ResolveRequest,
		) (skillcontext.ResolvedContext, error) {
			pageCalls++
			if request.SkillID != "travel" || request.Requirement.SlotID != "current_page" {
				t.Fatalf("resolver request = %#v", request)
			}
			return skillcontext.ResolvedContext{
				Kind:        "page",
				SourceRef:   "page:trip_1",
				Authority:   generated.AssistantContextAuthorityDeviceObserved,
				Sensitivity: generated.AssistantContextSensitivityInternal,
				CapturedAt:  now.Add(-time.Minute),
				ExpiresAt:   now.Add(time.Hour),
				TokenCost:   1200,
				Value:       map[string]any{"fullPage": "large"},
				ArtifactRef: "artifact:page_1",
				Summary:     "trip plan page summary",
			}, nil
		})},
		contextReaderBinding{descriptor: contextReaderDescriptor(
			"weather.unused", "domain",
			generated.AssistantContextAuthorityExternalEvidence,
			generated.AssistantContextSensitivityPublic,
		), resolver: contextResolverFunc(func(
			skillcontext.ResolveRequest,
		) (skillcontext.ResolvedContext, error) {
			unusedCalls++
			return skillcontext.ResolvedContext{}, nil
		})},
	)
	assembler := skillcontext.NewAssembler(registry)
	profile := skillcontext.Profile{
		ProfileID: "travel-context",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "current_page",
			Required:            true,
			AcceptedSourceKinds: []string{"page"},
			Authority:           generated.AssistantContextAuthorityDeviceObserved,
			Sensitivity:         generated.AssistantContextSensitivityInternal,
			Freshness:           10 * time.Minute,
			TokenBudget:         200,
			ResolverRef:         "page.current",
			FallbackPolicy:      "clarify",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := assembler.Assemble(context.Background(), profile, skillcontext.AssembleRequest{
		RunID:              "run_1",
		SkillID:            "travel",
		Visibility:         skillcontext.DeliveryPersonal,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	})
	if err != nil {
		t.Fatalf("Assemble() error = %v", err)
	}
	if pageCalls != 1 || unusedCalls != 0 {
		t.Fatalf("resolver calls = page %d unused %d", pageCalls, unusedCalls)
	}
	if len(snapshot.Segments) != 1 || snapshot.TokenCost != 200 || snapshot.SnapshotID == "" {
		t.Fatalf("snapshot = %#v", snapshot)
	}
	segment := snapshot.Segments[0]
	if segment.ArtifactRef != "artifact:page_1" || segment.Value["summary"] != "trip plan page summary" {
		t.Fatalf("artifact segment = %#v", segment)
	}
}

func TestSkillContextNeverInjectsPrivateMemoryIntoSharedOrPublicDelivery(t *testing.T) {
	now := time.Now().UTC()
	registry := contextReaderRegistry(t, contextReaderBinding{
		descriptor: contextReaderDescriptor(
			"memory.private", "memory",
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
		),
		resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			return skillcontext.ResolvedContext{
				Kind:        "memory",
				SourceRef:   "memory:user_1",
				Authority:   generated.AssistantContextAuthorityUserDeclared,
				Sensitivity: generated.AssistantContextSensitivityPrivate,
				CapturedAt:  now,
				TokenCost:   20,
				Value:       map[string]any{"preference": "private destination"},
			}, nil
		}),
	})
	profile := skillcontext.Profile{
		ProfileID: "travel-context",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "private_preference",
			Required:            true,
			AcceptedSourceKinds: []string{"memory"},
			Authority:           generated.AssistantContextAuthorityUserDeclared,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			TokenBudget:         100,
			ResolverRef:         "memory.private",
			FallbackPolicy:      "omit",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	for _, visibility := range []skillcontext.DeliveryVisibility{
		skillcontext.DeliveryShared,
		skillcontext.DeliveryPublic,
	} {
		t.Run(string(visibility), func(t *testing.T) {
			snapshot, err := skillcontext.NewAssembler(registry).Assemble(
				context.Background(),
				profile,
				skillcontext.AssembleRequest{
					RunID:              "run_1",
					SkillID:            "travel",
					Visibility:         visibility,
					AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
				},
			)
			if err != nil {
				t.Fatal(err)
			}
			if len(snapshot.Segments) != 0 || len(snapshot.Missing) != 1 {
				t.Fatalf("private memory escaped: %#v", snapshot)
			}
		})
	}
}

func TestSkillContextRejectsStaleOrWrongAuthorityResolverOutput(t *testing.T) {
	now := time.Now().UTC()
	registry := contextReaderRegistry(t, contextReaderBinding{
		descriptor: contextReaderDescriptor(
			"weather.current", "domain",
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPublic,
		),
		resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			return skillcontext.ResolvedContext{
				Kind:        "domain",
				SourceRef:   "weather:old",
				Authority:   generated.AssistantContextAuthorityExternalEvidence,
				Sensitivity: generated.AssistantContextSensitivityPublic,
				CapturedAt:  now.Add(-2 * time.Hour),
				TokenCost:   10,
				Value:       map[string]any{"temperature": 20},
			}, nil
		}),
	})
	profile := skillcontext.Profile{
		ProfileID: "weather-context",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "current_weather",
			Required:            true,
			AcceptedSourceKinds: []string{"domain"},
			Authority:           generated.AssistantContextAuthorityDomainCanonical,
			Freshness:           30 * time.Minute,
			Sensitivity:         generated.AssistantContextSensitivityPublic,
			TokenBudget:         100,
			ResolverRef:         "weather.current",
			FallbackPolicy:      "clarify",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := skillcontext.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		skillcontext.AssembleRequest{
			RunID:              "run_1",
			SkillID:            "weather",
			Visibility:         skillcontext.DeliveryPersonal,
			AllowedSensitivity: generated.AssistantContextSensitivityPublic,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Segments) != 0 || len(snapshot.Missing) != 1 || snapshot.Missing[0].FallbackPolicy != "clarify" {
		t.Fatalf("snapshot = %#v", snapshot)
	}
}

func TestSkillContextRejectsResolverThatDowngradesDeclaredSensitivity(t *testing.T) {
	now := time.Now().UTC()
	registry := contextReaderRegistry(t, contextReaderBinding{
		descriptor: contextReaderDescriptor(
			"trip.private", "domain",
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPrivate,
		),
		resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			return skillcontext.ResolvedContext{
				Kind:        "domain",
				SourceRef:   "travel.TripTimelineView:trip-1",
				Authority:   generated.AssistantContextAuthorityDomainCanonical,
				Sensitivity: generated.AssistantContextSensitivityPublic,
				CapturedAt:  now,
				TokenCost:   10,
				Value:       map[string]any{"hotelRoom": "private"},
			}, nil
		}),
	})
	profile := skillcontext.Profile{
		ProfileID: "travel-private",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "trip_private",
			Required:            true,
			AcceptedSourceKinds: []string{"domain"},
			Authority:           generated.AssistantContextAuthorityDomainCanonical,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			TokenBudget:         100,
			ResolverRef:         "trip.private",
			FallbackPolicy:      "block",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := skillcontext.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		skillcontext.AssembleRequest{
			RunID:              "run_1",
			SkillID:            "travel",
			Visibility:         skillcontext.DeliveryShared,
			AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Segments) != 0 || len(snapshot.Missing) != 1 {
		t.Fatalf("resolver sensitivity downgrade escaped policy: %#v", snapshot)
	}
}

func TestSkillContextConsentReaderIsFailClosedBeforeResolver(t *testing.T) {
	now := time.Now().UTC()
	resolverCalls := 0
	registry := contextReaderRegistry(t, contextReaderBinding{
		descriptor: contextReaderDescriptor(
			"trip.private", "domain",
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPrivate,
		),
		resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			resolverCalls++
			return skillcontext.ResolvedContext{
				Kind:        "domain",
				SourceRef:   "trip:user_1",
				Authority:   generated.AssistantContextAuthorityDomainCanonical,
				Sensitivity: generated.AssistantContextSensitivityPrivate,
				CapturedAt:  now,
				TokenCost:   20,
				Value:       map[string]any{"destination": "private"},
			}, nil
		}),
	})
	profile := skillcontext.Profile{
		ProfileID: "travel-consented-context",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "trip",
			Required:            true,
			AcceptedSourceKinds: []string{"domain"},
			Authority:           generated.AssistantContextAuthorityDomainCanonical,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			ConsentScopes:       []string{"trip.read"},
			TokenBudget:         100,
			ResolverRef:         "trip.private",
			FallbackPolicy:      "block",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	request := skillcontext.AssembleRequest{
		RunID:              "run_1",
		OwnerID:            "user_1",
		SkillID:            "travel",
		Visibility:         skillcontext.DeliveryPersonal,
		AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
	}
	tests := []struct {
		name    string
		consent skillcontext.ConsentReader
		allowed bool
	}{
		{name: "reader missing"},
		{
			name: "reader unavailable",
			consent: skillcontext.ConsentReaderFunc(func(
				context.Context, string, string, []string,
			) (bool, error) {
				return false, errors.New("consent store unavailable")
			}),
		},
		{
			name: "scope revoked",
			consent: skillcontext.ConsentReaderFunc(func(
				context.Context, string, string, []string,
			) (bool, error) {
				return false, nil
			}),
		},
		{
			name: "scope granted",
			consent: skillcontext.ConsentReaderFunc(func(
				_ context.Context,
				ownerID string,
				skillID string,
				scopes []string,
			) (bool, error) {
				if ownerID != "user_1" || skillID != "travel" ||
					len(scopes) != 1 || scopes[0] != "trip.read" {
					t.Fatalf(
						"consent request owner=%q skill=%q scopes=%v",
						ownerID,
						skillID,
						scopes,
					)
				}
				return true, nil
			}),
			allowed: true,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			before := resolverCalls
			assembler := skillcontext.NewAssembler(registry, test.consent)
			snapshot, assembleErr := assembler.Assemble(
				context.Background(),
				profile,
				request,
			)
			if assembleErr != nil {
				t.Fatal(assembleErr)
			}
			if test.allowed {
				if len(snapshot.Segments) != 1 || len(snapshot.Missing) != 0 ||
					resolverCalls != before+1 {
					t.Fatalf("granted snapshot=%#v calls=%d", snapshot, resolverCalls)
				}
				return
			}
			if len(snapshot.Segments) != 0 || len(snapshot.Missing) != 1 ||
				resolverCalls != before {
				t.Fatalf("fail-closed snapshot=%#v calls=%d", snapshot, resolverCalls)
			}
		})
	}
}
