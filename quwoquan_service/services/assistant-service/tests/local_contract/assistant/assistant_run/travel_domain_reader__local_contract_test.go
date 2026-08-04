// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strings"
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
	sourceDigest := canonicalTravelProjectionFixtureDigest("trip-1", "revision-2", 2)
	client, err := domainreader.NewTravelClient(
		"https://travel.local",
		travelDomainReaderHTTPClient(t, sourceDigest, "", requested),
		travelAuthorizationStub{},
	)
	if err != nil {
		t.Fatal(err)
	}

	result, err := client.ReadTripContext(t.Context(), "persona-1", "trip-1")
	if err != nil {
		t.Fatalf("ReadTripContext(): %v", err)
	}
	segments, _ := result.Map["segments"].([]any)
	if len(requested) != 3 || result.TripID != "trip-1" ||
		result.Map["revisionId"] != "revision-2" || len(segments) != 0 ||
		result.Map["currentRevisionId"] != nil || result.Map["routeSegments"] != nil ||
		len(result.GuideAssignments["assignments"].([]any)) != 1 {
		t.Fatalf("requested=%v result=%+v", requested, result)
	}
}

func TestTravelDomainReaderRejectsUnknownTripMapProjectionFields(t *testing.T) {
	sourceDigest := canonicalTravelProjectionFixtureDigest("trip-1", "revision-2", 2)
	client, err := domainreader.NewTravelClient(
		"https://travel.local",
		travelDomainReaderHTTPClient(
			t,
			sourceDigest,
			`,"providerUrl":"https://maps.example/route"`,
			nil,
		),
		travelAuthorizationStub{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := client.ReadTripContext(t.Context(), "persona-1", "trip-1"); err == nil {
		t.Fatal("ReadTripContext() accepted an undeclared provider URL")
	}
}

type travelRoundTripFunc func(*http.Request) (*http.Response, error)

func (roundTrip travelRoundTripFunc) RoundTrip(
	request *http.Request,
) (*http.Response, error) {
	return roundTrip(request)
}

func travelDomainReaderHTTPClient(
	t *testing.T,
	sourceDigest string,
	mapExtraFields string,
	requested map[string]int,
) *http.Client {
	t.Helper()
	return &http.Client{Transport: travelRoundTripFunc(func(
		request *http.Request,
	) (*http.Response, error) {
		if request.Method != http.MethodGet ||
			request.Header.Get("Authorization") != "Bearer travel-persona-1" {
			t.Fatalf(
				"request=%s %s authorization=%q",
				request.Method,
				request.URL.Path,
				request.Header.Get("Authorization"),
			)
		}
		if requested != nil {
			requested[request.URL.Path]++
		}
		body := ""
		switch request.URL.Path {
		case "/travel/trips/trip-1/timeline":
			body = fmt.Sprintf(`{"tripId":"trip-1","currentRevisionId":"revision-2","currentRevisionNumber":2,"sourceDigest":%q,"projectedAt":"2026-08-02T14:00:00Z","days":[],"sourceMomentIds":[],"sourceContentLinkIds":[]}`, sourceDigest)
		case "/travel/trips/trip-1/map":
			body = travelTripMapFixture(sourceDigest, mapExtraFields)
		case "/travel/trips/trip-1/guide-assignments":
			body = `{"tripId":"trip-1","assignments":[{"taskKey":"meeting","status":"assigned"}]}`
		default:
			return &http.Response{
				StatusCode: http.StatusNotFound,
				Header:     make(http.Header),
				Body:       io.NopCloser(strings.NewReader("not found")),
				Request:    request,
			}, nil
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(strings.NewReader(body)),
			Request:    request,
		}, nil
	})}
}

func travelTripMapFixture(sourceDigest, extraFields string) string {
	return fmt.Sprintf(`{
		"tripId":"trip-1",
		"currentRevisionId":"revision-2",
		"currentRevisionNumber":2,
		"sourceDigest":%q,
		"sourceEventId":"event-trip-map-2",
		"projectedAt":"2026-08-02T14:00:00Z",
		"sourceMomentIds":[],
		"sourceContentLinkIds":[],
		"stops":[{
			"stopId":"stop-1",
			"sequence":0,
			"dayIndex":0,
			"itemId":"item-1",
			"title":"断桥",
			"placeRef":{"objectTypeRef":"entity.Place","objectId":"place-broken-bridge"},
			"momentIds":[],
			"contentLinkIds":[]
		}],
		"routeSegments":[],
		"momentMarkers":[]%s
	}`, sourceDigest, extraFields)
}
