package main

import (
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/runtime/controlplane"
)

func TestResolveSnapshotPathUsesConfigRoot(t *testing.T) {
	got := resolveSnapshotPath("/etc/qwq-config", "product-ops-service", "product-ops-service-beta-control-a-0")
	want := "/etc/qwq-config/runtime-cache/product-ops-service/product-ops-service-beta-control-a-0.json"
	if got != want {
		t.Fatalf("expected %q, got %q", want, got)
	}
}

func TestResolveSnapshotPathUsesLocalCacheWhenConfigRootMissing(t *testing.T) {
	t.Setenv("QWQ_OUTPUT_ROOT", "/tmp/qwq-output")
	got := resolveSnapshotPath("", "product-ops-service", "product-ops-service-beta-control-a-0")
	want := "/tmp/qwq-output/env/repo/local/control-plane/process/product-ops-service/product-ops-service-beta-control-a-0.json"
	if got != want {
		t.Fatalf("expected %q, got %q", want, got)
	}
}

func TestResolveSnapshotPathUsesRepoOutputRootWhenEnvMissing(t *testing.T) {
	t.Setenv("QWQ_OUTPUT_ROOT", "")
	got := resolveSnapshotPath("", "product-ops-service", "product-ops-service-beta-control-a-0")
	wantSuffix := "/.qwq_output/env/repo/local/control-plane/process/product-ops-service/product-ops-service-beta-control-a-0.json"
	if !strings.HasSuffix(filepath.ToSlash(got), wantSuffix) {
		t.Fatalf("expected repo output root path ending %q, got %q", wantSuffix, got)
	}
}

func TestDefaultClusterNamePerEnvironment(t *testing.T) {
	cases := []struct {
		env  string
		want string
	}{
		{"beta", "beta-control-a"},
		{"gamma", "gamma-control-a"},
		{"prod", "prod-control-a"},
		{"alpha", "alpha-control-a"},
	}
	for _, tc := range cases {
		if got := defaultClusterName(tc.env); got != tc.want {
			t.Errorf("defaultClusterName(%q) = %q, want %q", tc.env, got, tc.want)
		}
	}
}

func TestHotConfigStoreIntegrationWithSnapshotRoundTrip(t *testing.T) {
	store := controlplane.NewHotConfigStore()
	resolved := []controlplane.ResolvedConfigValue{
		{Key: "sys.gateway.rate_limit.per_user_rps", Value: 50.0, ScopeLevel: "service", ScopeID: "product-ops-service"},
		{Key: "sys.orchestrator.downstream.timeout_ms", Value: 720.0, ScopeLevel: "service", ScopeID: "product-ops-service"},
	}
	effectiveHash := store.Apply(resolved)

	desiredHash := controlplane.EffectiveConfigHash(resolved)
	if effectiveHash != desiredHash {
		t.Fatalf("hash mismatch: effective=%s desired=%s", effectiveHash, desiredHash)
	}

	if got := store.GetInt("sys.gateway.rate_limit.per_user_rps", 0); got != 50 {
		t.Fatalf("expected 50, got %d", got)
	}
	if got := store.GetFloat("sys.orchestrator.downstream.timeout_ms", 0); got != 720.0 {
		t.Fatalf("expected 720.0, got %f", got)
	}
}
