// spec_ref: specs/feature-tree/discovery-content/content-service-contract-foundation/privacy-ui-config-contract/spec.md#gwt-001
package local_contract

import (
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestFeedRequestDefaultsAndCategoryTypesHaveOneContentSource(t *testing.T) {
	t.Parallel()
	serviceRoot := quwoquanServiceRoot(t)
	postDir := filepath.Join(serviceRoot, "services", "content-service", "contracts", "content", "post")

	operation := readContentFeedOperation(t, filepath.Join(postDir, "operations.yaml"))
	if operation.Pagination.DefaultItems != 20 || operation.Pagination.MaximumItems != 20 {
		t.Fatalf("GetFeed pagination=%+v want default=20 maximum=20", operation.Pagination)
	}
	if got := readContentFeedLimitDefault(t, filepath.Join(postDir, "fields.yaml")); got != "20" {
		t.Fatalf("ContentDiscoveryFeedQuery.limit client_default=%q want 20", got)
	}

	ui := readContentFeedUIConfig(t, filepath.Join(postDir, "ui_config.yaml"))
	want := map[string]string{
		"recommended": "micro",
		"following":   "micro",
		"micro":       "micro",
		"images":      "image",
		"video":       "video",
		"article":     "article",
	}
	if !reflect.DeepEqual(ui.FeedRequestTypeByCategory, want) {
		t.Fatalf(
			"feed_request_type_by_category=%v want canonical mapping %v",
			ui.FeedRequestTypeByCategory, want,
		)
	}
	contentTypes := readContentTypeSet(
		t, filepath.Join(serviceRoot, "contracts", "metadata", "_shared", "types.yaml"),
	)
	for category, contentType := range ui.FeedRequestTypeByCategory {
		if _, found := contentTypes[contentType]; !found {
			t.Errorf("feed category %q references unknown ContentType %q", category, contentType)
		}
	}
}

type contentFeedOperation struct {
	Operation  string `yaml:"operation"`
	Pagination struct {
		DefaultItems int `yaml:"default_items"`
		MaximumItems int `yaml:"maximum_items"`
	} `yaml:"pagination"`
}

func readContentFeedOperation(t *testing.T, path string) contentFeedOperation {
	t.Helper()
	var document struct {
		APIRoutes []contentFeedOperation `yaml:"api_routes"`
	}
	readContentPolicyYAML(t, path, &document)
	for _, operation := range document.APIRoutes {
		if operation.Operation == "GetFeed" {
			return operation
		}
	}
	t.Fatalf("GetFeed not found in %s", path)
	return contentFeedOperation{}
}

func readContentFeedLimitDefault(t *testing.T, path string) string {
	t.Helper()
	var document struct {
		Types map[string]struct {
			Fields []struct {
				Name          string `yaml:"name"`
				ClientDefault any    `yaml:"client_default"`
			} `yaml:"fields"`
		} `yaml:"types"`
	}
	readContentPolicyYAML(t, path, &document)
	entity := document.Types["ContentDiscoveryFeedQuery"]
	for _, field := range entity.Fields {
		if field.Name == "limit" {
			return fmt.Sprint(field.ClientDefault)
		}
	}
	t.Fatalf("ContentDiscoveryFeedQuery.limit not found in %s", path)
	return ""
}

type contentFeedUIConfig struct {
	FeedRequestTypeByCategory map[string]string `yaml:"feed_request_type_by_category"`
}

func readContentFeedUIConfig(t *testing.T, path string) contentFeedUIConfig {
	t.Helper()
	var document contentFeedUIConfig
	readContentPolicyYAML(t, path, &document)
	return document
}

func readContentTypeSet(t *testing.T, path string) map[string]struct{} {
	t.Helper()
	var document struct {
		Enums map[string][]string `yaml:"enums"`
	}
	readContentPolicyYAML(t, path, &document)
	result := make(map[string]struct{}, len(document.Enums["ContentType"]))
	for _, value := range document.Enums["ContentType"] {
		result[value] = struct{}{}
	}
	return result
}

func readContentPolicyYAML(t *testing.T, path string, target any) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(raw, target); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
}
