// Package runtimeconfig owns content Post runtime composition rules shared by
// the service startup and its contract validation.
package runtimeconfig

import (
	"os"
	"strings"
)

// RecommendationModelConfig is the runtime binding consumed by the content
// composition root. env tag 是相对后缀：完整键由 config struct 的
// envPrefix 链拼出（CONTENT_REC_MODEL_SERVICE_URL 等）。
type RecommendationModelConfig struct {
	URL       string `yaml:"url" env:"URL"`
	TimeoutMs int    `yaml:"timeout_ms" env:"TIMEOUT_MS"`
	Enabled   bool   `yaml:"enabled" env:"ENABLED"`
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
