package runtimegovernance

import "testing"

func TestFeatureEnabledUsesFallbackWhenUnset(t *testing.T) {
	t.Setenv("CHAT_GROUP_AVATAR_PRECOMPOSE_ENABLED", "")
	if !FeatureEnabled("chat.group_avatar_precompose_enabled", true) {
		t.Fatal("expected fallback true when env unset")
	}
}

func TestFeatureEnabledReadsExplicitFalse(t *testing.T) {
	t.Setenv("RUNTIME_AVATAR_PATCH_ENABLED", "false")
	if FeatureEnabled("runtime.avatar_patch_enabled", true) {
		t.Fatal("expected false when env is false")
	}
}

func TestPersonaContextEnabledDefaultsToTrue(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_MODEL_V2", "")
	t.Setenv("OPS_USER_PERSONA_CONTEXT_V1", "")
	if !PersonaContextEnabled() {
		t.Fatal("expected persona context flag to follow persona model default true")
	}
}

func TestPersonaContextEnabledReadsExplicitFalse(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_CONTEXT_V1", "false")
	if PersonaContextEnabled() {
		t.Fatal("expected persona context flag to read false")
	}
}

func TestPersonaGraphEnabledDefaultsToTrue(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_MODEL_V2", "")
	t.Setenv("OPS_USER_PERSONA_CONTEXT_V1", "")
	t.Setenv("OPS_USER_PERSONA_GRAPH_V1", "")
	t.Setenv("OPS_USER_PERSONA_GRAPH_V2", "")
	t.Setenv("OPS_USER_PERSONA_GRAPH_V1", "")
	if !PersonaGraphEnabled() {
		t.Fatal("expected persona graph flag to default to true through v2 fallback chain")
	}
}

func TestPersonaGraphEnabledReadsExplicitFalse(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_GRAPH_V2", "false")
	if PersonaGraphEnabled() {
		t.Fatal("expected persona graph v2 flag to read false")
	}
}

func TestPersonaModelAndPublicFlagsDefaultToTrue(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_MODEL_V2", "")
	t.Setenv("OPS_USER_PROFILE_SUBJECT_V1", "")
	if !PersonaModelEnabled() {
		t.Fatal("expected persona model flag to default true")
	}
	if !PersonaPublicProfileEnabled() {
		t.Fatal("expected persona public profile flag to default true")
	}
}

func TestPersonaSyncFallsBackToModelFlag(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_MODEL_V2", "false")
	t.Setenv("OPS_USER_PERSONA_SYNC_V2", "")
	if PersonaSyncEnabled() {
		t.Fatal("expected persona sync to follow persona model fallback false")
	}
}

func TestPersonaFlagSnapshotContainsAllRolloutFlags(t *testing.T) {
	t.Setenv("OPS_USER_PERSONA_GRAPH_V1", "false")
	snapshot := PersonaFlagSnapshot()
	for _, key := range []string{
		FlagPersonaModelV2,
		FlagPersonaSyncV2,
		FlagProfileSubjectV1,
		FlagPersonaContextV1,
		FlagPersonaGraphV1,
		FlagPersonaGraphV2,
	} {
		if _, ok := snapshot[key]; !ok {
			t.Fatalf("expected snapshot to include %s", key)
		}
	}
}
