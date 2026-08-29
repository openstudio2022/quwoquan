package local_contract

import (
	"path/filepath"
	"quwoquan_service/runtime/servicekit"
	. "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestRuntimeConfigDoesNotExposeProviderSelectorOverrides(t *testing.T) {
	t.Setenv("ASSISTANT_MODEL_PROVIDER", "deterministic")
	t.Setenv("ASSISTANT_SEARCH_PROVIDER", "duckduckgo_html")

	cfg := Config{}
	if err := servicekit.ApplyEnvOverrides(
		servicekit.DefaultEnvPrefix("assistant-service"), &cfg,
	); err != nil {
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
	var schema struct {
		Configs []struct {
			Key     string `yaml:"key"`
			Default any    `yaml:"default"`
		} `yaml:"configs"`
	}
	readAssistantAuthorityYAML(
		t,
		filepath.Join(root, "config", "schema.yaml"),
		&schema,
	)
	defaults := map[string]string{}
	for _, item := range schema.Configs {
		if value, ok := item.Default.(string); ok {
			defaults[item.Key] = value
		}
	}
	expected := map[string]map[string]string{
		"alpha": {
			"sys.assistant-service.chat_service.base_url": "http://chat-service:18081",
			"sys.assistant-service.user_service.base_url": "http://user-service:18081",
		},
		"beta": {
			"sys.assistant-service.chat_service.base_url": "http://chat-service:18081",
			"sys.assistant-service.user_service.base_url": "http://user-service:18081",
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
				got := defaults[key]
				if override, ok := config.Overrides[key]; ok {
					got = override
				}
				if got != want {
					t.Fatalf("%s=%q, want %q", key, got, want)
				}
			}
		})
	}
}
