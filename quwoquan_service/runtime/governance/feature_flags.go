package runtimegovernance

import (
	"os"
	"strings"
)

const (
	FlagPersonaModelV2   = "ops.user.persona_model_v2"
	FlagPersonaSyncV2    = "ops.user.persona_sync_v2"
	FlagPersonaGraphV2   = "ops.user.persona_graph_v2"
	FlagProfileSubjectV1 = "ops.user.profile_subject_v1"
	FlagPersonaContextV1 = "ops.user.persona_context_v1"
	FlagPersonaGraphV1   = "ops.user.persona_graph_v1"
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

func PersonaModelEnabled() bool {
	return FeatureEnabled(FlagPersonaModelV2, true)
}

func PersonaSyncEnabled() bool {
	return FeatureEnabled(FlagPersonaSyncV2, PersonaModelEnabled())
}

func PersonaPublicProfileEnabled() bool {
	return FeatureEnabled(FlagProfileSubjectV1, PersonaModelEnabled())
}

func PersonaContextEnabled() bool {
	return FeatureEnabled(FlagPersonaContextV1, PersonaModelEnabled())
}

func PersonaGraphEnabled() bool {
	return FeatureEnabled(FlagPersonaGraphV2, FeatureEnabled(FlagPersonaGraphV1, PersonaContextEnabled()))
}

func PersonaFlagSnapshot() map[string]bool {
	return map[string]bool{
		FlagPersonaModelV2:   PersonaModelEnabled(),
		FlagPersonaSyncV2:    PersonaSyncEnabled(),
		FlagProfileSubjectV1: PersonaPublicProfileEnabled(),
		FlagPersonaContextV1: PersonaContextEnabled(),
		FlagPersonaGraphV1:   FeatureEnabled(FlagPersonaGraphV1, PersonaContextEnabled()),
		FlagPersonaGraphV2:   PersonaGraphEnabled(),
	}
}
