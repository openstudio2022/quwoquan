package local_contract

import (
	"os"
	"path/filepath"
	"testing"

	circleconfig "quwoquan_service/services/circle-service/internal/circle_management/circle/infrastructure/runtimeconfig"
)

func TestDefaultClusterNamePerEnvironment(t *testing.T) {
	cases := map[string]string{
		"alpha": "alpha-control-a",
		"beta":  "beta-control-a",
		"gamma": "gamma-control-a",
		"prod":  "prod-control-a",
	}
	for appEnv, want := range cases {
		if got := circleconfig.DefaultClusterName(appEnv); got != want {
			t.Fatalf("DefaultClusterName(%q) = %q, want %q", appEnv, got, want)
		}
	}
}

func TestLoadCanonicalSnapshotIsRequired(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "circle-service.yaml")
	if err := os.WriteFile(path, []byte("config:\n  version: sha256:canonical\nservice:\n  http:\n    addr: ':18091'\n"), 0o600); err != nil {
		t.Fatalf("write canonical snapshot: %v", err)
	}
	var cfg struct {
		Config struct {
			Version string `yaml:"version"`
		} `yaml:"config"`
		Service struct {
			HTTP struct {
				Addr string `yaml:"addr"`
			} `yaml:"http"`
		} `yaml:"service"`
	}
	if err := circleconfig.LoadCanonicalSnapshot("circle-service", "gamma", root, &cfg); err != nil {
		t.Fatalf("load canonical external release config: %v", err)
	}
	if cfg.Config.Version != "sha256:canonical" || cfg.Service.HTTP.Addr != ":18091" {
		t.Fatalf("canonical snapshot drift: %#v", cfg)
	}
	if err := os.Remove(path); err != nil {
		t.Fatalf("remove canonical snapshot: %v", err)
	}
	if err := circleconfig.LoadCanonicalSnapshot("circle-service", "gamma", root, &cfg); err == nil {
		t.Fatal("missing canonical snapshot must fail startup")
	}
}
