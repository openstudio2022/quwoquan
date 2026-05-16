package projector

import (
	"context"
	"log/slog"
	"testing"

	"github.com/prometheus/client_golang/prometheus/testutil"

	"quwoquan_service/runtime/eventstore"
)

type stubProjector struct {
	name       string
	eventTypes []string
	err        error
}

func (s *stubProjector) Name() string                                                    { return s.name }
func (s *stubProjector) EventTypes() []string                                            { return s.eventTypes }
func (s *stubProjector) Project(_ context.Context, _ eventstore.StoredEvent) error { return s.err }

func TestDispatchIncreasesPrometheusCounters(t *testing.T) {
	d := NewDispatcher(slog.Default())
	d.Register(&stubProjector{name: "feed", eventTypes: []string{"post.published"}})

	event := eventstore.StoredEvent{
		ID:   "e1",
		Type: "post.published",
	}
	if err := d.Dispatch(context.Background(), event); err != nil {
		t.Fatal(err)
	}

	okVal := testutil.ToFloat64(projectorEventsTotal.WithLabelValues("feed", "post.published", "ok"))
	if okVal < 1 {
		t.Errorf("projector_events_total{status=ok}: expected >= 1, got %v", okVal)
	}

	durationCount := testutil.CollectAndCount(projectorDurationSeconds)
	if durationCount == 0 {
		t.Error("projector_duration_seconds should have at least one metric")
	}
}
