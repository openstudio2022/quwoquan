package runtimegovernance

import (
	"os"
	"strings"
)

// FeatureEnabled resolves an explicitly supported rollout switch. Stable
// domain models must not use this helper to revive retired schemas or behavior.
func FeatureEnabled(key string, fallback bool) bool {
	envKey := strings.NewReplacer(".", "_", "-", "_").Replace(strings.TrimSpace(key))
	envKey = strings.ToUpper(envKey)
	raw := strings.TrimSpace(os.Getenv(envKey))
	switch strings.ToLower(raw) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}
