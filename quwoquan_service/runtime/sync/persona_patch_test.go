package runtimesync

import (
	"context"
	"testing"

	personarollout "quwoquan_service/runtime/persona"
	rtredis "quwoquan_service/runtime/redis"
)

func TestAppendPersonaPatchStoresSupportedPatch(t *testing.T) {
	service := NewService(rtredis.NewMemoryClient(), rtredis.NewMemoryClient())

	patch, err := service.AppendPersonaPatch(context.Background(), "user_001", personarollout.PatchPersonaActivated, map[string]any{
		"personaId": "pa_001",
		"reason":    "switch",
	})
	if err != nil {
		t.Fatalf("expected append persona patch success, got %v", err)
	}
	if patch.Type != personarollout.PatchPersonaActivated {
		t.Fatalf("unexpected patch type: %s", patch.Type)
	}
}

func TestAppendPersonaPatchRejectsMissingPersonaID(t *testing.T) {
	service := NewService(rtredis.NewMemoryClient(), rtredis.NewMemoryClient())

	if _, err := service.AppendPersonaPatch(context.Background(), "user_001", personarollout.PatchPersonaActivated, map[string]any{}); err == nil {
		t.Fatal("expected missing personaId to fail")
	}
}

func TestAppendPersonaPatchRejectsUnsupportedPatchType(t *testing.T) {
	service := NewService(rtredis.NewMemoryClient(), rtredis.NewMemoryClient())

	if _, err := service.AppendPersonaPatch(context.Background(), "user_001", "user.avatar.updated", map[string]any{"personaId": "pa_001"}); err == nil {
		t.Fatal("expected unsupported patch type to fail")
	}
}
