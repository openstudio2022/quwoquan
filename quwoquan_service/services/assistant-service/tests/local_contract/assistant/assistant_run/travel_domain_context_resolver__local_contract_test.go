// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontextapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	skillcontextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
)

func TestTravelContextResolverUsesTypedTripReferenceAndPreservesSourceDigest(t *testing.T) {
	projectedAt := time.Date(2026, 8, 2, 14, 0, 0, 0, time.UTC)
	runs := travelRunReader{run: runruntime.Run{
		RunID: "run-trip", PersonaID: "persona-1",
		ContextSnapshot: map[string]any{
			"pageObjects": []any{map[string]any{
				"objectTypeRef": "travel.TripPlan", "objectId": "trip-1",
			}},
		},
	}}
	travel := &travelContextReader{value: domainreader.TravelContext{
		TripID: "trip-1", CurrentRevisionID: "revision-2", CurrentRevisionNumber: 2,
		SourceDigest: "sha256:travel-source", ProjectedAt: projectedAt,
		Timeline: map[string]any{
			"tripId": "trip-1", "days": []any{map[string]any{"dayIndex": 0}},
			"sourceMomentIds": []any{"moment-1"}, "sourceContentLinkIds": []any{"link-1"},
		},
		Map: map[string]any{"tripId": "trip-1", "stops": []any{map[string]any{"stopId": "stop-1"}}},
		GuideAssignments: map[string]any{
			"tripId": "trip-1", "assignments": []any{map[string]any{"taskKey": "meeting"}},
		},
	}}
	resolver := skillcontextinfra.TravelContextResolver{Runs: runs, Travel: travel}
	resolved, err := resolver.Resolve(t.Context(), skillcontextapplication.ResolveRequest{
		RunID: "run-trip", SkillID: "travel_companion",
	})
	if err != nil {
		t.Fatalf("Resolve(): %v", err)
	}
	if travel.personaID != "persona-1" || travel.tripID != "trip-1" ||
		resolved.Kind != "domain" || resolved.SourceRef != "travel.TripTimelineView:trip-1@sha256:travel-source" ||
		resolved.ArtifactRef != resolved.SourceRef || !resolved.CapturedAt.Equal(projectedAt) ||
		resolved.Summary == "" || resolved.Value["sourceDigest"] != "sha256:travel-source" ||
		resolved.Value["guideAssignments"] == nil {
		t.Fatalf("travel=%+v resolved=%+v", travel, resolved)
	}
}

func TestTravelContextResolverDoesNotInferTripIdentityFromFreeText(t *testing.T) {
	resolver := skillcontextinfra.TravelContextResolver{
		Runs: travelRunReader{run: runruntime.Run{
			RunID: "run-trip", PersonaID: "persona-1", InputText: "看看 trip-secret 的行程",
		}},
		Travel: &travelContextReader{},
	}
	if _, err := resolver.Resolve(t.Context(), skillcontextapplication.ResolveRequest{
		RunID: "run-trip", SkillID: "travel_companion",
	}); err == nil {
		t.Fatal("Resolve() inferred a Trip identity from untrusted free text")
	}
}

func TestTravelContextResolverIgnoresClientTopLevelTripID(t *testing.T) {
	travel := &travelContextReader{}
	resolver := skillcontextinfra.TravelContextResolver{
		Runs: travelRunReader{run: runruntime.Run{
			RunID: "run-trip", PersonaID: "persona-1",
			ContextSnapshot: map[string]any{"tripId": "trip-secret"},
		}},
		Travel: travel,
	}
	if _, err := resolver.Resolve(t.Context(), skillcontextapplication.ResolveRequest{
		RunID: "run-trip", SkillID: "travel_companion",
	}); err == nil {
		t.Fatal("Resolve() accepted an untrusted top-level Trip identity")
	}
	if travel.personaID != "" || travel.tripID != "" {
		t.Fatalf("untrusted Trip identity reached domain reader: %+v", travel)
	}
}

type travelRunReader struct {
	run runruntime.Run
}

func (reader travelRunReader) Load(_ context.Context, runID string) (runruntime.Run, error) {
	if runID != reader.run.RunID {
		return runruntime.Run{}, runruntime.ErrRunNotFound
	}
	return reader.run, nil
}

type travelContextReader struct {
	value     domainreader.TravelContext
	err       error
	personaID string
	tripID    string
}

func (reader *travelContextReader) ReadTripContext(
	_ context.Context,
	personaID string,
	tripID string,
) (domainreader.TravelContext, error) {
	reader.personaID = personaID
	reader.tripID = tripID
	if reader.err != nil {
		return domainreader.TravelContext{}, reader.err
	}
	if reader.value.TripID == "" {
		return domainreader.TravelContext{}, errors.New("unexpected read")
	}
	return reader.value, nil
}
