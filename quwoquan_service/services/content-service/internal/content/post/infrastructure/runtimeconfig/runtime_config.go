// Package runtimeconfig owns content Post runtime composition rules shared by
// the service startup and its contract validation.
package runtimeconfig

import (
	"os"
	"strconv"
	"strings"
)

// RecommendationModelConfig is the runtime binding consumed by the content
// composition root.
type RecommendationModelConfig struct {
	URL       string `yaml:"url"`
	TimeoutMs int    `yaml:"timeout_ms"`
	Enabled   bool   `yaml:"enabled"`
}

// ContentSliceWorkload reports whether the current process is serving one of
// the bounded immutable-release content workloads.
func ContentSliceWorkload() bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv("QWQ_WORKLOAD"))) {
	case "content-release", "content-commercial":
		return true
	default:
		return false
	}
}

// ApplyRecommendationModelEnvOverrides applies the deployment-owned model
// endpoint overrides without changing invalid values into implicit defaults.
func ApplyRecommendationModelEnvOverrides(cfg *RecommendationModelConfig) {
	if cfg == nil {
		return
	}
	if value := os.Getenv("REC_MODEL_SERVICE_URL"); value != "" {
		cfg.URL = value
	}
	if value := os.Getenv("REC_MODEL_SERVICE_ENABLED"); value != "" {
		if enabled, err := strconv.ParseBool(value); err == nil {
			cfg.Enabled = enabled
		}
	}
	if value := os.Getenv("REC_MODEL_SERVICE_TIMEOUT_MS"); value != "" {
		if milliseconds, err := strconv.Atoi(value); err == nil && milliseconds > 0 {
			cfg.TimeoutMs = milliseconds
		}
	}
}
