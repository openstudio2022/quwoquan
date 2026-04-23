package application

import (
	"encoding/json"
	"net/http"
)

type RuntimeMediaAlertThresholds struct {
	GroupAvatarRecomputeDurationMsP95 float64 `json:"groupAvatarRecomputeDurationMsP95"`
	GroupAvatarFallbackRatio          float64 `json:"groupAvatarFallbackRatio"`
	HintToPullDelayMsP95              float64 `json:"hintToPullDelayMsP95"`
	PatchFanoutFailureRatio           float64 `json:"patchFanoutFailureRatio"`
}

type runtimeMediaSyncMetrics interface {
	MetricsSnapshot() map[string]float64
}

func NewRuntimeMediaMetricsHandler(
	scheduler *RedisGroupAvatarTaskScheduler,
	sync runtimeMediaSyncMetrics,
	thresholds RuntimeMediaAlertThresholds,
) http.HandlerFunc {
	return func(w http.ResponseWriter, _ *http.Request) {
		payload := map[string]any{
			"thresholds": thresholds,
			"metrics": map[string]map[string]float64{
				"groupAvatarTask": map[string]float64{},
				"sync":            map[string]float64{},
			},
		}
		if scheduler != nil {
			payload["metrics"].(map[string]map[string]float64)["groupAvatarTask"] = scheduler.MetricsSnapshot()
		}
		if sync != nil {
			payload["metrics"].(map[string]map[string]float64)["sync"] = sync.MetricsSnapshot()
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(payload)
	}
}
