package learning_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/learning"
	"testing"
	"time"

	runtimelearning "quwoquan_service/runtime/learning"
)

func TestMongoSinkRejectsNonTimestampOccurredAt(t *testing.T) {
	sink := &MongoSink{}
	err := sink.FlushEvents(context.Background(), []runtimelearning.Event{{
		EventID:    "invalid_occurred_at",
		OccurredAt: "not-a-timestamp",
	}})
	if err == nil {
		t.Fatal("Mongo learning sink must reject a non-RFC3339 occurredAt value")
	}
}

func TestMongoSinkRejectsNonTimestampFeatureSnapshotAt(t *testing.T) {
	sink := &MongoSink{}
	err := sink.FlushEvents(context.Background(), []runtimelearning.Event{{
		EventID:    "invalid_feature_snapshot_at",
		OccurredAt: "2026-07-21T00:00:00Z",
		Context: map[string]any{
			"featureSnapshotAt": "not-a-timestamp",
		},
	}})
	if err == nil {
		t.Fatal("Mongo learning sink must reject an invalid featureSnapshotAt")
	}
}

func TestNormalizeLearningEventContextStoresSnapshotAsUTCDateTime(t *testing.T) {
	normalized, err := NormalizeLearningEventContext("snapshot_event", map[string]any{
		"featureSnapshotAt": "2026-07-21T08:30:00+08:00",
	})
	if err != nil {
		t.Fatalf("normalize feature snapshot: %v", err)
	}
	snapshotAt, ok := normalized["featureSnapshotAt"].(time.Time)
	if !ok {
		t.Fatalf("featureSnapshotAt type=%T, want time.Time", normalized["featureSnapshotAt"])
	}
	if got, want := snapshotAt.Format(time.RFC3339Nano), "2026-07-21T00:30:00Z"; got != want {
		t.Fatalf("featureSnapshotAt=%q, want %q", got, want)
	}
}
