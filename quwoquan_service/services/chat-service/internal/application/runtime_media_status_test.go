package application

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
)

type fakeRuntimeMediaSyncMetrics struct {
	snapshot map[string]float64
}

func (f fakeRuntimeMediaSyncMetrics) MetricsSnapshot() map[string]float64 {
	return f.snapshot
}

func TestRuntimeMediaMetricsHandlerReturnsThresholdsAndMetrics(t *testing.T) {
	router := rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {Mode: "memory"},
		},
		DefaultScene: "general",
	})
	t.Cleanup(func() {
		_ = router.Close()
	})

	scheduler := NewRedisGroupAvatarTaskScheduler(
		router.Scene("general"),
		nil,
		nil,
		nil,
		nil,
		nil,
	)
	if err := scheduler.EnqueueRecompute(context.Background(), GroupAvatarRecomputeTask{
		ConversationID: "conv_001",
		ActorID:        "user_001",
		Trigger:        "test",
	}); err != nil {
		t.Fatalf("EnqueueRecompute: %v", err)
	}

	handler := NewRuntimeMediaMetricsHandler(
		scheduler,
		fakeRuntimeMediaSyncMetrics{
			snapshot: map[string]float64{
				"quwoquan_runtime_media_sync_pull_total": 3,
			},
		},
		RuntimeMediaAlertThresholds{
			GroupAvatarRecomputeDurationMsP95: 400,
			GroupAvatarFallbackRatio:          0.02,
			HintToPullDelayMsP95:              1500,
			PatchFanoutFailureRatio:           0.01,
		},
	)

	req := httptest.NewRequest(http.MethodGet, "/metrics/runtime-media", nil)
	rec := httptest.NewRecorder()
	handler.ServeHTTP(rec, req)

	if rec.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", rec.Code)
	}

	var payload struct {
		Thresholds RuntimeMediaAlertThresholds   `json:"thresholds"`
		Metrics    map[string]map[string]float64 `json:"metrics"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("Unmarshal response: %v", err)
	}

	if payload.Thresholds.GroupAvatarRecomputeDurationMsP95 != 400 {
		t.Fatalf("unexpected recompute threshold: %+v", payload.Thresholds)
	}
	if payload.Metrics["sync"]["quwoquan_runtime_media_sync_pull_total"] != 3 {
		t.Fatalf("unexpected sync metric snapshot: %+v", payload.Metrics["sync"])
	}
	if payload.Metrics["groupAvatarTask"][metricGroupAvatarTaskQueueDepth] != 1 {
		t.Fatalf("expected queue depth 1, got %+v", payload.Metrics["groupAvatarTask"])
	}
}
