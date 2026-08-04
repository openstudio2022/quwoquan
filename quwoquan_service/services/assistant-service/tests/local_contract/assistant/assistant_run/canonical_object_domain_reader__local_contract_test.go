// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	contextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

func TestCanonicalDomainResolverRegistrationUsesOneTrustedObjectTarget(t *testing.T) {
	now := time.Date(2026, 8, 4, 9, 0, 0, 0, time.UTC)
	runs := canonicalObjectRunReader{run: runruntime.Run{
		RunID: "run-object",
		ContextSnapshot: map[string]any{"pageObjects": []any{
			map[string]any{"objectTypeRef": "entity.Homepage", "objectId": "homepage-1"},
			map[string]any{"objectTypeRef": "content.Post", "objectId": "post-1"},
		}},
	}}
	content := &canonicalObjectReaderStub{value: domainreader.ObjectContext{
		Target:       domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "post-1"},
		OperationRef: "content.post.GetPost",
		CapturedAt:   now,
		SourceDigest: "sha256:" + strings.Repeat("a", 64),
		TokenCost:    17,
		Value:        map[string]any{"postId": "post-1", "visibility": "public"},
		Summary:      "content.Post post-1",
	}}
	registrations, err := contextinfra.NewCanonicalDomainResolverRegistrations(
		runs,
		domainreader.CanonicalReaders{
			Circle: &canonicalObjectReaderStub{}, Content: content, Entity: &canonicalObjectReaderStub{},
		},
	)
	if err != nil || len(registrations) != 3 {
		t.Fatalf("registrations=%+v err=%v", registrations, err)
	}
	var contentResolver application.Resolver
	for _, registration := range registrations {
		if registration.ResolverRef == contextinfra.ContentContextResolverRef {
			contentResolver = registration.Resolver
		}
	}
	if contentResolver == nil {
		t.Fatal("content resolver registration is unavailable")
	}
	resolved, err := contentResolver.Resolve(t.Context(), application.ResolveRequest{
		RunID: "run-object", SkillID: "travel_companion",
	})
	if err != nil {
		t.Fatal(err)
	}
	if content.target != (domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "post-1"}) ||
		resolved.Kind != "domain" || resolved.Authority != generated.AssistantContextAuthorityDomainCanonical ||
		resolved.Sensitivity != generated.AssistantContextSensitivityPublic ||
		resolved.SourceRef != "content.Post:post-1@sha256:"+strings.Repeat("a", 64) ||
		!resolved.CapturedAt.Equal(now) || resolved.ArtifactRef != "" {
		t.Fatalf("reader target=%+v resolved=%+v", content.target, resolved)
	}
}

func TestCanonicalDomainReaderCompositionBuildsOneRuntimeRegistry(t *testing.T) {
	descriptors, err := contextinfra.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	reader := &canonicalObjectReaderStub{}
	registry, err := contextinfra.NewRuntimeRegistryWithCanonicalReaders(
		catalog,
		canonicalObjectRunReader{run: runruntime.Run{RunID: "run-composition"}},
		nil,
		nil,
		domainreader.CanonicalReaders{Circle: reader, Content: reader, Entity: reader},
	)
	if err != nil {
		t.Fatal(err)
	}
	for _, resolverRef := range []string{
		contextinfra.CircleContextResolverRef,
		contextinfra.ContentContextResolverRef,
		contextinfra.EntityContextResolverRef,
	} {
		descriptor, ok := registry.Describe(t.Context(), resolverRef)
		if !ok || descriptor.ResolverRef != resolverRef {
			t.Fatalf("resolver %q is absent from production registry: %+v", resolverRef, descriptor)
		}
	}
}

func TestCanonicalDomainResolverRejectsAmbiguousAndMismatchedProvenance(t *testing.T) {
	reader := &canonicalObjectReaderStub{}
	resolver := contextinfra.ObjectContextResolver{
		Runs: canonicalObjectRunReader{run: runruntime.Run{
			RunID: "run-ambiguous",
			ContextSnapshot: map[string]any{"pageObjects": []any{
				map[string]any{"objectTypeRef": "content.Post", "objectId": "post-1"},
				map[string]any{"objectTypeRef": "content.Post", "objectId": "post-2"},
			}},
		}},
		Reader: reader, OperationRef: "content.post.GetPost",
		ObjectTypeRefs: []string{"content.Post"},
	}
	if _, err := resolver.Resolve(t.Context(), application.ResolveRequest{RunID: "run-ambiguous"}); err == nil {
		t.Fatal("ambiguous page objects were accepted")
	}
	if reader.calls != 0 {
		t.Fatalf("ambiguous target reached owner Reader calls=%d", reader.calls)
	}

	reader.value = domainreader.ObjectContext{
		Target:       domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "forged"},
		OperationRef: "content.post.GetPost", CapturedAt: time.Now().UTC(),
		SourceDigest: "sha256:" + strings.Repeat("b", 64), Value: map[string]any{"postId": "forged"},
	}
	resolver.Runs = canonicalObjectRunReader{run: runruntime.Run{
		RunID: "run-mismatch",
		ContextSnapshot: map[string]any{"pageObjects": []any{
			map[string]any{"objectTypeRef": "content.Post", "objectId": "post-1"},
		}},
	}}
	if _, err := resolver.Resolve(t.Context(), application.ResolveRequest{RunID: "run-mismatch"}); err == nil {
		t.Fatal("mismatched owner provenance was accepted")
	}
}

func TestContextAssemblerRejectsMalformedEntityCitation(t *testing.T) {
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID: "content.post_context", ResolverRef: "content.current_context",
		OwnerService:       "content-service",
		OwnerOperationRefs: []string{"content.post.GetPost"},
		InputSchemaRef:     "content.ContentPostDetailQuery", OutputSchemaRef: "assistant.ContextSegment",
		ObjectTypeRefs: []string{"content.Post"}, AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityPublic,
		MaxFreshnessSeconds: 300,
		SurfaceKinds:        []readermodel.SurfaceKind{readermodel.SurfacePublic},
		ArtifactPolicy:      readermodel.ArtifactInlineBounded,
		CitationPolicy:      readermodel.CitationEntityReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog([]readermodel.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	registry, err := application.NewResolverRegistry(catalog, application.RegisteredResolver{
		ResolverRef: descriptor.ResolverRef,
		Resolver: contextResolverFunc(func(application.ResolveRequest) (application.ResolvedContext, error) {
			return application.ResolvedContext{
				Kind: "domain", SourceRef: "https://example.invalid/post-1",
				Authority:   generated.AssistantContextAuthorityDomainCanonical,
				Sensitivity: generated.AssistantContextSensitivityPublic,
				CapturedAt:  time.Now().UTC(), TokenCost: 8,
				Value: map[string]any{"postId": "post-1"},
			}, nil
		}),
	})
	if err != nil {
		t.Fatal(err)
	}
	profile := application.Profile{
		ProfileID: "citation",
		Requirements: []application.Requirement{{
			SlotID: "content", Required: true, AcceptedSourceKinds: []string{"domain"},
			Authority:   generated.AssistantContextAuthorityDomainCanonical,
			Sensitivity: generated.AssistantContextSensitivityPublic,
			Freshness:   time.Minute, TokenBudget: 128,
			ResolverRef: descriptor.ResolverRef, FallbackPolicy: "block",
		}},
	}
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := application.NewAssembler(registry).Assemble(
		t.Context(),
		profile,
		application.AssembleRequest{
			RunID: "run-citation", SkillID: "travel_companion",
			Visibility:         application.DeliveryPublic,
			AllowedSensitivity: generated.AssistantContextSensitivityPublic,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Segments) != 0 || len(snapshot.Missing) != 1 {
		t.Fatalf("malformed citation crossed context boundary: %+v", snapshot)
	}
}

type canonicalObjectRunReader struct{ run runruntime.Run }

func (reader canonicalObjectRunReader) Load(_ context.Context, runID string) (runruntime.Run, error) {
	if strings.TrimSpace(runID) != reader.run.RunID {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return reader.run, nil
}

type canonicalObjectReaderStub struct {
	value  domainreader.ObjectContext
	err    error
	target domainreader.ObjectTarget
	calls  int
}

func (reader *canonicalObjectReaderStub) ReadObjectContext(
	_ context.Context,
	target domainreader.ObjectTarget,
) (domainreader.ObjectContext, error) {
	reader.calls++
	reader.target = target
	return reader.value, reader.err
}
