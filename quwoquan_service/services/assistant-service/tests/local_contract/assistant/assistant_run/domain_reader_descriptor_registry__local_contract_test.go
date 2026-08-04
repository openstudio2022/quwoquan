// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/generated/operationsecurity"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

func TestCanonicalDomainReaderDescriptorsBindOnlyGeneratedOwnerOperations(t *testing.T) {
	knownOperations := map[string]struct{}{}
	for _, domain := range []string{"assistant", "circle", "content", "entity", "travel", "user"} {
		for _, operation := range operationsecurity.ForDomain(domain) {
			knownOperations[operation.CanonicalOperationID] = struct{}{}
		}
	}
	descriptors, err := skillcontextinfra.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	for _, descriptor := range descriptors {
		if !strings.HasPrefix(descriptor.DescriptorDigest, "sha256:") ||
			len(descriptor.DescriptorDigest) != len("sha256:")+64 {
			t.Fatalf("descriptor %q digest=%q", descriptor.ResolverRef, descriptor.DescriptorDigest)
		}
		for _, operationRef := range descriptor.OwnerOperationRefs {
			if _, exists := knownOperations[operationRef]; !exists {
				t.Fatalf("descriptor %q has non-canonical owner operation %q", descriptor.ResolverRef, operationRef)
			}
		}
	}
	publicReaders := map[string]string{
		"circle.current_context":  "circle.Circle",
		"content.current_context": "content.Post",
		"entity.current_context":  "entity.Homepage",
	}
	for resolverRef, objectTypeRef := range publicReaders {
		var found *readermodel.Descriptor
		for index := range descriptors {
			if descriptors[index].ResolverRef == resolverRef {
				found = &descriptors[index]
				break
			}
		}
		if found == nil || found.Sensitivity != generated.AssistantContextSensitivityPublic ||
			found.ArtifactPolicy != readermodel.ArtifactInlineBounded ||
			found.CitationPolicy != readermodel.CitationEntityReference ||
			!containsValue(found.ObjectTypeRefs, objectTypeRef) ||
			!containsSurface(found.SurfaceKinds, readermodel.SurfacePublic) {
			t.Fatalf("public Reader %q boundary=%+v", resolverRef, found)
		}
	}
}

func containsValue(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func containsSurface(values []readermodel.SurfaceKind, wanted readermodel.SurfaceKind) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func TestContextProfileCannotWidenRegisteredReaderBoundary(t *testing.T) {
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID:        "travel.private_trip",
		ResolverRef:         "trip.private",
		OwnerService:        "travel-service",
		OwnerOperationRefs:  []string{"travel.trip_timeline_view.GetTripTimeline"},
		InputSchemaRef:      "travel.GetTripTimelineQuery",
		OutputSchemaRef:     "assistant.TravelContextSegment",
		AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityPrivate,
		SurfaceKinds:        []readermodel.SurfaceKind{readermodel.SurfacePersonal},
		ArtifactPolicy:      readermodel.ArtifactInlineOrStored,
		CitationPolicy:      readermodel.CitationEntityReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog([]readermodel.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	registry, err := skillcontext.NewResolverRegistry(catalog, skillcontext.RegisteredResolver{
		ResolverRef: descriptor.ResolverRef,
		Resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			t.Fatal("resolver must not execute after profile widens descriptor")
			return skillcontext.ResolvedContext{}, nil
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	profile := skillcontext.Profile{
		ProfileID: "widened",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "trip",
			Required:            true,
			AcceptedSourceKinds: []string{"domain", "memory"},
			Authority:           generated.AssistantContextAuthorityDomainCanonical,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			ResolverRef:         "trip.private",
			FallbackPolicy:      "block",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	_, err = skillcontext.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		skillcontext.AssembleRequest{
			RunID:              "run-1",
			SkillID:            "travel_companion",
			Visibility:         skillcontext.DeliveryShared,
			AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
		},
	)
	if err == nil {
		t.Fatal("widened ContextProfile was accepted")
	}
}

func TestOptionalPersonalReaderIsOmittedAtSharedSurfaceBeforeResolution(t *testing.T) {
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID:        "assistant.private_input",
		ResolverRef:         "turn.private_input",
		OwnerService:        "assistant-service",
		OwnerOperationRefs:  []string{"assistant.assistant_run.GetAssistantRun"},
		InputSchemaRef:      "assistant.GetAssistantRunQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		AcceptedSourceKinds: []string{"conversation"},
		Authority:           generated.AssistantContextAuthorityUserDeclared,
		Sensitivity:         generated.AssistantContextSensitivityPrivate,
		SurfaceKinds:        []readermodel.SurfaceKind{readermodel.SurfacePersonal},
		ArtifactPolicy:      readermodel.ArtifactInlineBounded,
		CitationPolicy:      readermodel.CitationSourceReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog([]readermodel.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	resolverCalled := false
	registry, err := skillcontext.NewResolverRegistry(catalog, skillcontext.RegisteredResolver{
		ResolverRef: descriptor.ResolverRef,
		Resolver: contextResolverFunc(func(skillcontext.ResolveRequest) (skillcontext.ResolvedContext, error) {
			resolverCalled = true
			return skillcontext.ResolvedContext{}, nil
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	profile := skillcontext.Profile{
		ProfileID: "shared-surface",
		Requirements: []skillcontext.Requirement{{
			SlotID:              "private_input",
			AcceptedSourceKinds: []string{"conversation"},
			Authority:           generated.AssistantContextAuthorityUserDeclared,
			Sensitivity:         generated.AssistantContextSensitivityPrivate,
			ResolverRef:         descriptor.ResolverRef,
			FallbackPolicy:      "omit",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := skillcontext.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		skillcontext.AssembleRequest{
			RunID:              "run-shared",
			SkillID:            "travel_companion",
			Visibility:         skillcontext.DeliveryShared,
			AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if resolverCalled || len(snapshot.Segments) != 0 || len(snapshot.Missing) != 0 {
		t.Fatalf("personal Reader crossed shared boundary: called=%v snapshot=%#v", resolverCalled, snapshot)
	}
}
