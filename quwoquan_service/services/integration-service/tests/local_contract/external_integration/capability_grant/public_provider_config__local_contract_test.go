// spec_ref: specs/feature-tree/runtime/runtime-external-integration/user-connector-capability-gateway/spec.md#gwt-001
package capability_grant_test

import (
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

const publicProviderConfigPrefix = "sys.integration-service.integration.public_provider."

func TestPublicProviderRetryPolicyHasBoundedDefaults(t *testing.T) {
	var config integrationconfig.Config
	integrationconfig.NormalizeDefaults(&config)
	for name, policy := range map[string]integrationconfig.PublicProviderPolicyConfig{
		"poi":   config.Integration.PublicProvider.POI,
		"route": config.Integration.PublicProvider.Route,
	} {
		if policy.RetryMaxAttempts != 2 || policy.RetryBackoffMs != 200 {
			t.Fatalf("%s retry policy=%+v", name, policy)
		}
	}
}

func TestPublicProviderEnvironmentConfigsOnlyOverrideRealDifferences(t *testing.T) {
	serviceRoot := integrationServiceRoot(t)
	schemaData, err := os.ReadFile(filepath.Join(serviceRoot, "config", "schema.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var schema struct {
		Configs []struct {
			Key     string `yaml:"key"`
			Default any    `yaml:"default"`
		} `yaml:"configs"`
	}
	if err := yaml.Unmarshal(schemaData, &schema); err != nil {
		t.Fatal(err)
	}
	defaults := map[string]any{}
	for _, definition := range schema.Configs {
		if strings.HasPrefix(definition.Key, publicProviderConfigPrefix) {
			defaults[definition.Key] = definition.Default
		}
	}
	if len(defaults) != 12 {
		t.Fatalf("public provider schema defaults=%d, want 12", len(defaults))
	}

	for _, environment := range []string{"alpha", "beta", "gamma", "prod"} {
		t.Run(environment, func(t *testing.T) {
			data, err := os.ReadFile(filepath.Join(
				serviceRoot,
				"environments",
				environment,
				"config.yaml",
			))
			if err != nil {
				t.Fatal(err)
			}
			var config struct {
				Overrides        map[string]any            `yaml:"overrides"`
				ExternalBindings map[string]map[string]any `yaml:"externalBindings"`
				Inherits         any                       `yaml:"inherits"`
				Extends          any                       `yaml:"extends"`
			}
			if err := yaml.Unmarshal(data, &config); err != nil {
				t.Fatal(err)
			}
			if config.Inherits != nil || config.Extends != nil {
				t.Fatalf("%s config must remain autonomous", environment)
			}
			for key, value := range config.Overrides {
				if defaultValue, exists := defaults[key]; exists &&
					reflect.DeepEqual(value, defaultValue) {
					t.Fatalf(
						"%s override %s duplicates schema default %#v",
						environment,
						key,
						value,
					)
				}
			}
			// nonprod 三环境共享同一 binding 档（DEC-005），alpha 不再单独启用。
			poiBinding := config.ExternalBindings["location.poi.search"]
			if len(poiBinding) != 1 || poiBinding["state"] != "not_required" {
				t.Fatalf(
					"%s location.poi.search binding must remain exactly not_required: %#v",
					environment,
					poiBinding,
				)
			}
			routeBinding := config.ExternalBindings["location.route.read"]
			if len(routeBinding) != 1 || routeBinding["state"] != "not_required" {
				t.Fatalf(
					"%s location.route.read binding must remain exactly not_required: %#v",
					environment,
					routeBinding,
				)
			}
			var document any
			if err := yaml.Unmarshal(data, &document); err != nil {
				t.Fatal(err)
			}
			if path, found := forbiddenProviderMaterialPath(document, ""); found {
				t.Fatalf("%s config embeds provider material at %s", environment, path)
			}
		})
	}
}

func forbiddenProviderMaterialPath(value any, path string) (string, bool) {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			childPath := key
			if path != "" {
				childPath = path + "." + key
			}
			if key == "endpoint" || key == "token" {
				return childPath, true
			}
			if foundPath, found := forbiddenProviderMaterialPath(child, childPath); found {
				return foundPath, true
			}
		}
	case []any:
		for index, child := range typed {
			childPath := path + "[" + strconv.Itoa(index) + "]"
			if foundPath, found := forbiddenProviderMaterialPath(child, childPath); found {
				return foundPath, true
			}
		}
	}
	return "", false
}
