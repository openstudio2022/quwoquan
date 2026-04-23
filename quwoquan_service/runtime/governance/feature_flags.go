package runtimegovernance

import (
	"os"
	"strings"
)

// FeatureEnabled resolves a boolean feature flag from environment variables.
// Example key: chat.group_avatar_precompose_enabled -> CHAT_GROUP_AVATAR_PRECOMPOSE_ENABLED
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
