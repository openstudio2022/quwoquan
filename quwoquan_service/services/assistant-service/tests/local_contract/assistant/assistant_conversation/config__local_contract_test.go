package local_contract

import (
	"path/filepath"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimeconfig"
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

func TestProactiveDeliveryDependenciesAreConfiguredInEveryEnvironment(
	t *testing.T,
) {
	root := assistantServiceRoot(t)
	expected := map[string]map[string]string{
		"alpha": {
			"sys.assistant-service.chat_service.base_url": "http://127.0.0.1:18082",
			"sys.assistant-service.user_service.base_url": "http://127.0.0.1:18081",
		},
		"beta": {
			"sys.assistant-service.chat_service.base_url": "http://127.0.0.1:18082",
			"sys.assistant-service.user_service.base_url": "http://127.0.0.1:18081",
		},
		"gamma": {
			"sys.assistant-service.chat_service.base_url": "http://chat-service:18081",
			"sys.assistant-service.user_service.base_url": "http://user-service:18081",
		},
		"prod": {
			"sys.assistant-service.chat_service.base_url": "http://chat-service:18081",
			"sys.assistant-service.user_service.base_url": "http://user-service:18081",
		},
	}
	for environment, values := range expected {
		t.Run(environment, func(t *testing.T) {
			var config struct {
				Overrides map[string]string `yaml:"overrides"`
			}
			readAssistantAuthorityYAML(
				t,
				filepath.Join(
					root,
					"environments",
					environment,
					"config.yaml",
				),
				&config,
			)
			for key, want := range values {
				if got := config.Overrides[key]; got != want {
					t.Fatalf("%s=%q, want %q", key, got, want)
				}
			}
		})
	}
}
