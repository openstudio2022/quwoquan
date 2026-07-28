package local_contract

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

func TestCreatorReleaseProjectionUsesUserServiceDatabaseAuthority(t *testing.T) {
	root := userServiceRoot(t)
	raw, err := os.ReadFile(filepath.Join(root, "config", "schema.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	var schema struct {
		Configs []struct {
			Key     string `yaml:"key"`
			Default any    `yaml:"default"`
		} `yaml:"configs"`
	}
	if err := yaml.Unmarshal(raw, &schema); err != nil {
		t.Fatal(err)
	}
	database := ""
	for _, config := range schema.Configs {
		if config.Key == "sys.user-service.mongodb.database" {
			database = strings.TrimSpace(fmt.Sprint(config.Default))
			break
		}
	}
	if database != "quwoquan_user" {
		t.Fatalf("creator release projection database drift: %q", database)
	}

	compose, err := os.ReadFile(filepath.Join(root, "deploy", "compose.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(compose), "MONGODB_DATABASE:") {
		t.Fatal("compose must not override the metadata-owned MongoDB database")
	}
}

func userServiceRoot(t *testing.T) string {
	t.Helper()
	current, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		candidate := filepath.Join(current, "services", "user-service")
		if _, err := os.Stat(filepath.Join(candidate, "config", "schema.yaml")); err == nil {
			return candidate
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatal("user-service root not found")
		}
		current = parent
	}
}
