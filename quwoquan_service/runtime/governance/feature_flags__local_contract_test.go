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
