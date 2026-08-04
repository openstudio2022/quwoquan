// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/application"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

func TestDescriptorDigestCoversPolicyAndRejectsStaleImmutableDigest(t *testing.T) {
	descriptor := testDescriptor("travel.trip", "trip.current_context")
	if !strings.HasPrefix(descriptor.DescriptorDigest, "sha256:") ||
		len(descriptor.DescriptorDigest) != len("sha256:")+64 {
		t.Fatalf("descriptor digest=%q", descriptor.DescriptorDigest)
	}

	widened := descriptor.Clone()
	widened.SurfaceKinds = append(widened.SurfaceKinds, model.SurfacePublic)
	if _, err := model.NewDescriptor(widened); !errors.Is(err, model.ErrInvalidDescriptor) {
		t.Fatalf("stale digest after policy widening error=%v", err)
	}
	widened.DescriptorDigest = ""
	updated, err := model.NewDescriptor(widened)
	if err != nil {
		t.Fatal(err)
	}
	if updated.DescriptorDigest == descriptor.DescriptorDigest {
		t.Fatal("surface policy change did not change descriptor digest")
	}
	invalid := descriptor.Clone()
	invalid.DescriptorDigest = ""
	invalid.AcceptedSourceKinds = append(invalid.AcceptedSourceKinds, " ")
	if _, err := model.NewDescriptor(invalid); !errors.Is(err, model.ErrInvalidDescriptor) {
		t.Fatalf("blank source kind error=%v", err)
	}
}

func TestCatalogIsImmutableUniqueAndSharedByQueryService(t *testing.T) {
	first := testDescriptor("assistant.input", "turn.slot")
	second := testDescriptor("travel.trip", "trip.current_context")
	catalog, err := resource.NewCatalog([]model.Descriptor{second, first})
	if err != nil {
		t.Fatal(err)
	}

	listed, err := catalog.ListDescriptors(context.Background(), 100)
	if err != nil {
		t.Fatal(err)
	}
	if len(listed) != 2 || listed[0].DescriptorID != "assistant.input" ||
		listed[1].DescriptorID != "travel.trip" {
		t.Fatalf("catalog ordering=%+v", listed)
	}
	listed[0].AcceptedSourceKinds[0] = "mutated"
	reloaded, err := catalog.GetDescriptor(context.Background(), "assistant.input")
	if err != nil || reloaded.AcceptedSourceKinds[0] != "domain" {
		t.Fatalf("catalog resource was mutated: descriptor=%+v err=%v", reloaded, err)
	}
	if _, err := resource.NewCatalog([]model.Descriptor{first, first}); err == nil {
		t.Fatal("duplicate descriptorId/resolverRef was accepted")
	}

	queries := application.NewQueryService(catalog)
	view, err := queries.ListDescriptors(
		context.Background(),
		application.ListDescriptorsQuery{Limit: 1},
	)
	if err != nil || len(view.Items) != 1 || view.Items[0].DescriptorID != "assistant.input" {
		t.Fatalf("ListDescriptors view=%+v err=%v", view, err)
	}
	detail, err := queries.GetDescriptor(
		context.Background(),
		application.GetDescriptorQuery{DescriptorID: "travel.trip"},
	)
	if err != nil || detail.ResolverRef != "trip.current_context" {
		t.Fatalf("GetDescriptor view=%+v err=%v", detail, err)
	}
}

func TestDescriptorQueriesFailClosedForInvalidMissingAndUnavailableCatalog(t *testing.T) {
	queries := application.NewQueryService(nil)
	_, err := queries.GetDescriptor(
		context.Background(),
		application.GetDescriptorQuery{},
	)
	assertAppError(t, err, "ASSISTANT.USER.domain_reader_invalid_argument", 400)
	_, err = queries.ListDescriptors(
		context.Background(),
		application.ListDescriptorsQuery{Limit: 100},
	)
	assertAppError(t, err, "ASSISTANT.SYSTEM.domain_reader_catalog_unavailable", 503)

	catalog, err := resource.NewCatalog([]model.Descriptor{
		testDescriptor("assistant.input", "turn.slot"),
	})
	if err != nil {
		t.Fatal(err)
	}
	queries = application.NewQueryService(catalog)
	_, err = queries.GetDescriptor(
		context.Background(),
		application.GetDescriptorQuery{DescriptorID: "missing"},
	)
	assertAppError(t, err, "ASSISTANT.USER.domain_reader_descriptor_not_found", 404)
	_, err = queries.ListDescriptors(
		context.Background(),
		application.ListDescriptorsQuery{Limit: 101},
	)
	assertAppError(t, err, "ASSISTANT.USER.domain_reader_invalid_argument", 400)
}

func testDescriptor(descriptorID string, resolverRef string) model.Descriptor {
	descriptor, err := model.NewDescriptor(model.Descriptor{
		DescriptorID:        descriptorID,
		ResolverRef:         resolverRef,
		OwnerService:        "travel-service",
		OwnerOperationRefs:  []string{"travel.trip_timeline_view.GetTripTimeline"},
		InputSchemaRef:      "travel.GetTripTimelineQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"travel.TripTimelineView"},
		AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityInternal,
		MaxFreshnessSeconds: 900,
		CacheTTLSeconds:     60,
		SurfaceKinds:        []model.SurfaceKind{model.SurfacePersonal, model.SurfaceShared},
		ArtifactPolicy:      model.ArtifactInlineOrStored,
		CitationPolicy:      model.CitationEntityReference,
	})
	if err != nil {
		panic(err)
	}
	return descriptor
}

func assertAppError(t *testing.T, err error, code string, status int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error=%T %v, want *runtimeerrors.AppError", err, err)
	}
	if appErr.Code.String() != code || appErr.HTTPStatus != status {
		t.Fatalf("error=%s/%d, want %s/%d", appErr.Code.String(), appErr.HTTPStatus, code, status)
	}
}
