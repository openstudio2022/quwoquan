package providerbinding

import (
	"strings"
	"testing"

	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/internal/generated"
)

func TestResolveFailsClosedForUnknownBlockedAndIncompleteBindings(t *testing.T) {
	config := runtimeconfig.MapRuntimeConfigProvider{Values: map[string]string{}}
	if _, err := Resolve("unknown", "assistant.model.generation", config); err == nil {
		t.Fatal("unknown binding must fail closed")
	}
	if _, err := Resolve("beta", "assistant.model.generation", config); err == nil ||
		!strings.Contains(err.Error(), "not enabled") {
		t.Fatalf("blocked binding error = %v", err)
	}

	original := assistantgenerated.ExternalProviderBindings["beta"]["assistant.model.generation"]
	enabled := original
	enabled.State = "enabled"
	assistantgenerated.ExternalProviderBindings["beta"]["assistant.model.generation"] = enabled
	t.Cleanup(func() {
		assistantgenerated.ExternalProviderBindings["beta"]["assistant.model.generation"] = original
	})

	if _, err := Resolve("beta", "assistant.model.generation", config); err == nil ||
		!strings.Contains(err.Error(), "endpoint material is unavailable") {
		t.Fatalf("missing endpoint material error = %v", err)
	}
	_, err := Resolve("beta", "assistant.model.generation", runtimeconfig.MapRuntimeConfigProvider{
		Values: map[string]string{
			"ASSISTANT_MODEL_COMPLETION_URL": "https://model.example.test/v1/chat/completions",
		},
	})
	if err == nil || !strings.Contains(err.Error(), "secret material is unavailable") {
		t.Fatalf("missing secret material error = %v", err)
	}
}
