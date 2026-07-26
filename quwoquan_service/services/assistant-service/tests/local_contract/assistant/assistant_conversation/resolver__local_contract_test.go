package local_contract

import (
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/providerbinding"
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
)

func TestResolveFailsClosedForUnknownBlockedAndIncompleteBindings(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := Resolve("unknown", "assistant.model.generation", config); err == nil {
		t.Fatal("unknown binding must fail closed")
	}

	original := assistantgenerated.ExternalProviderBindings["prod"]["assistant.model.generation"]
	blocked := original
	blocked.State = "blocked"
	assistantgenerated.ExternalProviderBindings["prod"]["assistant.model.generation"] = blocked
	if _, err := Resolve("prod", "assistant.model.generation", config); err == nil ||
		!strings.Contains(err.Error(), "not enabled") {
		t.Fatalf("blocked binding error = %v", err)
	}

	enabled := original
	enabled.State = "enabled"
	assistantgenerated.ExternalProviderBindings["prod"]["assistant.model.generation"] = enabled
	t.Cleanup(func() {
		assistantgenerated.ExternalProviderBindings["prod"]["assistant.model.generation"] = original
	})

	if _, err := Resolve("prod", "assistant.model.generation", config); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("missing endpoint material error = %v", err)
	}
	_, err := Resolve("prod", "assistant.model.generation", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"ASSISTANT_MODEL_COMPLETION_URL": "https://model.example.test/v1/chat/completions",
		},
	})
	if err == nil || !strings.Contains(err.Error(), "secret material is unavailable") {
		t.Fatalf("missing secret material error = %v", err)
	}
}
