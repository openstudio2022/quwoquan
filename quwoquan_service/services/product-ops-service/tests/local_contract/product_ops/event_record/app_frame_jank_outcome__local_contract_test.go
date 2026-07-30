package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestFrameJankOutcomeAcceptsZeroJankyFramesAndRejectsNegativeValues(t *testing.T) {
	store := telemetrypersistence.NewMemoryTelemetryStore()
	service := application.NewTelemetryService(store, store)
	occurredAt := time.Now().UTC().Add(-time.Minute)
	event := validEvent("app_frame_jank_outcome", "event", occurredAt)
	sampledFrames, jankyFrames := 120, 0
	worstFrameMS, jankThresholdMS := 16, 50
	result := "ok"
	event.SampledFrames = &sampledFrames
	event.JankyFrames = &jankyFrames
	event.WorstFrameMS = &worstFrameMS
	event.JankThresholdMS = &jankThresholdMS
	event.Result = &result

	ack, err := service.ReportEventBatch(
		context.Background(),
		digestKey("clean-frame-batch"),
		[]application.EventRecordInput{event},
	)
	if err != nil || ack.AcceptedCount != 1 {
		t.Fatalf("zero-jank frame batch must be accepted: ack=%+v err=%v", ack, err)
	}

	negativeJankyFrames := -1
	event.JankyFrames = &negativeJankyFrames
	if _, err := service.ReportEventBatch(
		context.Background(),
		digestKey("invalid-negative-frame-batch"),
		[]application.EventRecordInput{event},
	); err == nil {
		t.Fatal("negative jankyFrames must remain invalid")
	}
}
