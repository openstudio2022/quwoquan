package controlplane_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"gopkg.in/yaml.v3"
)

type assistantOnboardingDoc struct {
	ServiceNames   []string `yaml:"service_names"`
	BlockingGaps   []string `yaml:"blocking_gaps"`
	ControlPlanes  struct {
		Platform struct {
			Enabled bool `yaml:"enabled"`
		} `yaml:"platform"`
		Product struct {
			Enabled bool `yaml:"enabled"`
		} `yaml:"product"`
	} `yaml:"control_planes"`
	MinimumPackage struct {
		TestEvidence struct {
			T2 []string `yaml:"t2"`
			T3 []string `yaml:"t3"`
		} `yaml:"test_evidence"`
	} `yaml:"minimum_package"`
}

func TestAssistantSeedboxControlPlaneContract(t *testing.T) {
	root := locateRepoRoot(t)
	data, err := os.ReadFile(filepath.Join(root, "contracts", "metadata", "_control_plane", "domains", "assistant.yaml"))
	if err != nil {
		t.Fatalf("read assistant onboarding metadata: %v", err)
	}

	var doc assistantOnboardingDoc
	if err := yaml.Unmarshal(data, &doc); err != nil {
		t.Fatalf("unmarshal assistant onboarding metadata: %v", err)
	}

	if !contains(doc.ServiceNames, "seed-box") {
		t.Fatalf("assistant domain must bind to seed-box service, got %v", doc.ServiceNames)
	}
	if !doc.ControlPlanes.Platform.Enabled || !doc.ControlPlanes.Product.Enabled {
		t.Fatalf("assistant domain must enable both platform and product control planes")
	}
	if len(doc.MinimumPackage.TestEvidence.T2) == 0 {
		t.Fatalf("assistant domain must include T2 evidence")
	}
	if len(doc.MinimumPackage.TestEvidence.T3) == 0 {
		t.Fatalf("assistant domain must include T3 evidence")
	}
	if len(doc.BlockingGaps) > 0 {
		t.Fatalf("assistant domain blocking gaps should be cleared before integration pass: %v", doc.BlockingGaps)
	}
}

func locateRepoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("get wd: %v", err)
	}
	current := wd
	for {
		if _, err := os.Stat(filepath.Join(current, "contracts", "metadata")); err == nil {
			return current
		}
		parent := filepath.Dir(current)
		if parent == current {
			t.Fatalf("repo root not found from %s", wd)
		}
		current = parent
	}
}

func contains(items []string, target string) bool {
	for _, item := range items {
		if strings.TrimSpace(item) == target {
			return true
		}
	}
	return false
}
