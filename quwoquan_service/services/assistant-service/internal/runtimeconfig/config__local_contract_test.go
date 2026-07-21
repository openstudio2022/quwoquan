package runtimeconfig

import (
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRuntimeConfigDoesNotExposeProviderSelectorOverrides(t *testing.T) {
	t.Setenv("ASSISTANT_MODEL_PROVIDER", "deterministic")
	t.Setenv("ASSISTANT_SEARCH_PROVIDER", "duckduckgo_html")

	cfg := Config{}
	if err := ApplyEnvOverrides(&cfg); err != nil {
		t.Fatalf("ApplyEnvOverrides() error = %v", err)
	}
	encoded, err := yaml.Marshal(cfg)
	if err != nil {
		t.Fatalf("marshal config: %v", err)
	}
	for _, forbidden := range []string{
		"model_provider:",
		"search_provider:",
		"deterministic",
		"duckduckgo_html",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("runtime config retains provider selector %q: %s", forbidden, encoded)
		}
	}
}
