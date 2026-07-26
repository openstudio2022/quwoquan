package local_contract

import (
	"context"
	"testing"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/feedback_fact/application"
	signalapplication "quwoquan_service/services/search-service/internal/search/recommendation_signal_fact/application"
)

type feedbackSinkRecorder struct {
	events []feedbackapplication.Event
	metas  []feedbackapplication.CommandMeta
}

func (recorder *feedbackSinkRecorder) Record(
	_ context.Context,
	event feedbackapplication.Event,
	meta feedbackapplication.CommandMeta,
) error {
	recorder.events = append(recorder.events, event)
	recorder.metas = append(recorder.metas, meta)
	return nil
}

type searchSignalRecorder struct {
	signals []signalapplication.Signal
}

func (recorder *searchSignalRecorder) PublishSearchSignal(
	_ context.Context,
	signal signalapplication.Signal,
) error {
	recorder.signals = append(recorder.signals, signal)
	return nil
}

func TestFeedbackReplayWithFreshTransportKeyKeepsOneSemanticSignalID(t *testing.T) {
	sink := &feedbackSinkRecorder{}
	signals := &searchSignalRecorder{}
	service := feedbackapplication.NewService(
		sink,
		feedbackapplication.WithSignalPublisher(signals),
	)
	event := feedbackapplication.Event{
		SearchRequestID: " request-1 ",
		ViewerID:        " persona-1 ",
		EventType:       " click ",
		ObjectID:        " post-1 ",
		Target:          " article ",
		RankPosition:    1,
	}
	for _, meta := range []feedbackapplication.CommandMeta{
		{IdempotencyKey: " transport-key-1 ", CommandDigest: " digest-1 "},
		{IdempotencyKey: "transport-key-2", CommandDigest: "digest-1"},
	} {
		if err := service.Report(context.Background(), event, meta); err != nil {
			t.Fatalf("report feedback: %v", err)
		}
	}
	if len(signals.signals) != 2 {
		t.Fatalf("signals=%d want=2 retry attempts", len(signals.signals))
	}
	if signals.signals[0].SignalID != signals.signals[1].SignalID {
		t.Fatalf(
			"semantic replay changed signal id: %q != %q",
			signals.signals[0].SignalID,
			signals.signals[1].SignalID,
		)
	}
	if len(signals.signals[0].EngagedObjectIDs) != 1 ||
		signals.signals[0].EngagedObjectIDs[0] != "post-1" ||
		sink.events[0].SearchRequestID != "request-1" ||
		sink.events[0].ViewerID != "persona-1" ||
		sink.metas[0].IdempotencyKey != "transport-key-1" {
		t.Fatalf(
			"feedback was not canonicalized: event=%+v meta=%+v signal=%+v",
			sink.events[0],
			sink.metas[0],
			signals.signals[0],
		)
	}
}
