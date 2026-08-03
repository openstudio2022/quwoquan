// spec_ref: specs/feature-tree/travel-journey/collaborative-trip-lifecycle/trip-plan-revision/spec.md#gwt-001
package local_contract

import (
	"context"
	"testing"
	"time"

	runtimemessaging "quwoquan_service/runtime/messaging"
	domaineventing "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/eventing"
	"quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/ports"
	tripmessaging "quwoquan_service/services/travel-service/internal/travel/trip_plan/infrastructure/messaging"
)

func TestTripPlanStreamPublisherUsesDurableTypedEventStream(t *testing.T) {
	transport := &tripDurableTransport{}
	publisher, err := tripmessaging.NewStreamPublisher(transport)
	if err != nil {
		t.Fatal(err)
	}
	err = publisher.Publish(t.Context(), ports.OutboxEvent{
		EventID: "event-trip-1", EventType: "TripPlanRevised",
		AggregateID: "trip-1", AggregateVersion: 2,
		Payload:    map[string]any{"currentRevisionNumber": int64(2)},
		OccurredAt: time.Date(2026, 8, 2, 14, 0, 0, 0, time.UTC),
	})
	if err != nil {
		t.Fatal(err)
	}
	if transport.message.Stream != tripmessaging.TripPlanEventStream ||
		transport.retention != 30*24*time.Hour || len(transport.message.Fields) == 0 {
		t.Fatalf("message=%+v retention=%s", transport.message, transport.retention)
	}
}

func TestTravelEventRoutesIncludeTemplateAndGuideAssignmentOutboxes(t *testing.T) {
	testCases := []struct {
		eventType     string
		stream        string
		aggregateType string
	}{
		{
			eventType:     "TripPlanTemplateChanged",
			stream:        domaineventing.TripPlanTemplateStream,
			aggregateType: "TripPlanTemplate",
		},
		{
			eventType:     "TripGuideAssignmentChanged",
			stream:        domaineventing.TripGuideAssignmentStream,
			aggregateType: "TripGuideAssignment",
		},
	}
	for _, testCase := range testCases {
		route, found := domaineventing.RouteForEvent(testCase.eventType)
		if !found || route.Stream != testCase.stream || route.AggregateType != testCase.aggregateType {
			t.Fatalf("RouteForEvent(%q)=(%+v,%t)", testCase.eventType, route, found)
		}
	}
}

type tripDurableTransport struct {
	message   runtimemessaging.DurableMessage
	retention time.Duration
}

func (transport *tripDurableTransport) AppendDurable(
	_ context.Context,
	message runtimemessaging.DurableMessage,
) (string, error) {
	transport.message = message
	return "1-0", nil
}

func (transport *tripDurableTransport) SetDurableRetention(
	_ context.Context,
	_ string,
	retention time.Duration,
) error {
	transport.retention = retention
	return nil
}
