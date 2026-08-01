package local_contract

import (
	"context"
	"testing"
	"time"

	feedbackapplication "quwoquan_service/services/search-service/internal/search/search_feedback_fact/application"
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

func TestFeedbackReplayWithFreshTransportKeyKeepsOneSemanticSignalID(t *testing.T) {
	sink := &feedbackSinkRecorder{}
	service := feedbackapplication.NewService(sink)
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
	createdAt := time.Date(
		2026,
		time.July,
		26,
		12,
		0,
		0,
		0,
		time.UTC,
	)
	firstSignal, firstOK := feedbackapplication.RecommendationSignal(
		sink.events[0],
		createdAt,
	)
	secondSignal, secondOK := feedbackapplication.RecommendationSignal(
		sink.events[1],
		createdAt,
	)
	if !firstOK || !secondOK {
		t.Fatal("canonical click feedback must produce a signal")
	}
	if firstSignal.SignalID != secondSignal.SignalID {
		t.Fatalf(
			"semantic replay changed signal id: %q != %q",
			firstSignal.SignalID,
			secondSignal.SignalID,
		)
	}
	if len(firstSignal.EngagedObjectIDs) != 1 ||
		firstSignal.EngagedObjectIDs[0] != "post-1" ||
		sink.events[0].SearchRequestID != "request-1" ||
		sink.events[0].ViewerID != "persona-1" ||
		sink.metas[0].IdempotencyKey != "transport-key-1" {
		t.Fatalf(
			"feedback was not canonicalized: event=%+v meta=%+v signal=%+v",
			sink.events[0],
			sink.metas[0],
			firstSignal,
		)
	}
}

func TestDwellFeedbackRequiresPositiveDuration(t *testing.T) {
	sink := &feedbackSinkRecorder{}
	service := feedbackapplication.NewService(sink)
	meta := feedbackapplication.CommandMeta{
		IdempotencyKey: "dwell-key",
		CommandDigest:  "dwell-digest",
	}
	if err := service.Report(context.Background(), feedbackapplication.Event{
		SearchRequestID: "request-dwell",
		EventType:       "dwell",
		DwellMs:         1,
	}, meta); err != nil {
		t.Fatalf("positive dwell feedback rejected: %v", err)
	}
	if len(sink.events) != 1 || sink.events[0].DwellMs != 1 {
		t.Fatalf("positive dwell feedback was not persisted: %+v", sink.events)
	}
	if err := service.Report(context.Background(), feedbackapplication.Event{
		SearchRequestID: "request-dwell-invalid",
		EventType:       "dwell",
	}, feedbackapplication.CommandMeta{
		IdempotencyKey: "dwell-invalid-key",
		CommandDigest:  "dwell-invalid-digest",
	}); err == nil {
		t.Fatal("dwell feedback without a positive duration must be rejected")
	}
}
