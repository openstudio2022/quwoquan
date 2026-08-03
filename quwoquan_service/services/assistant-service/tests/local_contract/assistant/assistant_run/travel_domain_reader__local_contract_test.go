// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
)

type travelAuthorizationStub struct{}

func (travelAuthorizationStub) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	return "Bearer travel-" + personaID, nil
}

func TestTravelDomainReaderLoadsTimelineMapAndGuideTasksWithOneDelegatedIdentity(t *testing.T) {
	requested := map[string]int{}
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet || request.Header.Get("Authorization") != "Bearer travel-persona-1" {
			t.Fatalf("request=%s %s authorization=%q", request.Method, request.URL.Path, request.Header.Get("Authorization"))
		}
		requested[request.URL.Path]++
		writer.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/travel/trips/trip-1/timeline":
			_, _ = writer.Write([]byte(`{"tripId":"trip-1","currentRevisionId":"revision-2","currentRevisionNumber":2,"sourceDigest":"sha256:source","projectedAt":"2026-08-02T14:00:00Z","days":[],"sourceMomentIds":[],"sourceContentLinkIds":[]}`))
		case "/travel/trips/trip-1/map":
			_, _ = writer.Write([]byte(`{"tripId":"trip-1","currentRevisionId":"revision-2","currentRevisionNumber":2,"sourceDigest":"sha256:source","stops":[]}`))
		case "/travel/trips/trip-1/guide-assignments":
			_, _ = writer.Write([]byte(`{"tripId":"trip-1","assignments":[{"taskKey":"meeting","status":"assigned"}]}`))
		default:
			http.NotFound(writer, request)
		}
	}))
	t.Cleanup(server.Close)
	client, err := domainreader.NewTravelClient(server.URL, server.Client(), travelAuthorizationStub{})
	if err != nil {
		t.Fatal(err)
	}

	result, err := client.ReadTripContext(t.Context(), "persona-1", "trip-1")
	if err != nil {
		t.Fatalf("ReadTripContext(): %v", err)
	}
	if len(requested) != 3 || result.TripID != "trip-1" ||
		len(result.GuideAssignments["assignments"].([]any)) != 1 {
		t.Fatalf("requested=%v result=%+v", requested, result)
	}
}
