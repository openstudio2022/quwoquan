package local_contract

import (
	"crypto/sha256"
	"fmt"
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
	canonicalDigest := fmt.Sprintf(
		"sha256:%x",
		sha256.Sum256([]byte("circle-service:canonical-config")),
	)
	config := fmt.Sprintf(
		"config:\n  version: %s\nservice:\n  http:\n    addr: ':18091'\n",
		canonicalDigest,
	)
	if err := os.WriteFile(path, []byte(config), 0o600); err != nil {
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
	if cfg.Config.Version != canonicalDigest || cfg.Service.HTTP.Addr != ":18091" {
		t.Fatalf("canonical snapshot drift: %#v", cfg)
	}
	if err := os.Remove(path); err != nil {
		t.Fatalf("remove canonical snapshot: %v", err)
	}
	if err := circleconfig.LoadCanonicalSnapshot("circle-service", "gamma", root, &cfg); err == nil {
		t.Fatal("missing canonical snapshot must fail startup")
	}
}
