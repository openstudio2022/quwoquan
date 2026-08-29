package servicekit

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLoadYAMLConfigFailsClosedWithoutSnapshot(t *testing.T) {
	identity := Identity{
		ServiceName: "circle-service",
		AppEnv:      "alpha",
		ConfigRoot:  t.TempDir(),
	}
	var target struct{}
	if err := LoadYAMLConfig(identity, &target); err == nil {
		t.Fatal("expected error when the rendered snapshot is missing")
	}
}

func TestLoadYAMLConfigReadsRenderedSnapshot(t *testing.T) {
	root := t.TempDir()
	snapshot := "config:\n  version: sha256:abc\nservice:\n  http:\n    addr: \":18082\"\n"
	if err := os.WriteFile(
		filepath.Join(root, "circle-service.yaml"), []byte(snapshot), 0o644,
	); err != nil {
		t.Fatal(err)
	}

	identity := Identity{
		ServiceName: "circle-service",
		AppEnv:      "alpha",
		ConfigRoot:  root,
	}
	var target struct {
		Config struct {
			Version string `yaml:"version"`
		} `yaml:"config"`
		Service struct {
			HTTP struct {
				Addr string `yaml:"addr"`
			} `yaml:"http"`
		} `yaml:"service"`
	}
	if err := LoadYAMLConfig(identity, &target); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if target.Config.Version != "sha256:abc" || target.Service.HTTP.Addr != ":18082" {
		t.Fatalf("unexpected decoded config: %+v", target)
	}
}

func TestValidateConfigIdentityRejectsVersionMismatch(t *testing.T) {
	identity := Identity{
		ServiceName:   "circle-service",
		ConfigVersion: "sha256:expected",
		ImageVersion:  "sha256:1111111111111111111111111111111111111111111111111111111111111111",
	}
	err := ValidateConfigIdentity("sha256:other", identity)
	if err == nil || !strings.Contains(err.Error(), "CONFIG_VERSION mismatch") {
		t.Fatalf("expected mismatch error, got %v", err)
	}
}

func TestValidateConfigIdentityRequiresImmutableImageVersion(t *testing.T) {
	identity := Identity{ServiceName: "circle-service", ConfigVersion: "sha256:abc"}
	for _, imageVersion := range []string{"", "latest"} {
		identity.ImageVersion = imageVersion
		if err := ValidateConfigIdentity("sha256:abc", identity); err == nil {
			t.Fatalf("expected IMAGE_VERSION rejection for %q", imageVersion)
		}
	}
	identity.ImageVersion = "sha256:2222222222222222222222222222222222222222222222222222222222222222"
	if err := ValidateConfigIdentity("sha256:abc", identity); err != nil {
		t.Fatalf("unexpected error for immutable image version: %v", err)
	}
}

func TestDefaultClusterNameDerivation(t *testing.T) {
	cases := map[string]string{
		"alpha": "alpha-control-a",
		"beta":  "beta-control-a",
		"gamma": "gamma-control-a",
		"prod":  "prod-control-a",
	}
	for environment, expected := range cases {
		if actual := DefaultClusterName(environment); actual != expected {
			t.Fatalf("DefaultClusterName(%s)=%s, expected %s", environment, actual, expected)
		}
	}
}
