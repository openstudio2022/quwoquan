package controlplane

import (
	"path/filepath"
	"reflect"
	"testing"
)

func TestResolveSnapshotSaveLoadRoundTrip(t *testing.T) {
	t.Helper()

	path := filepath.Join(t.TempDir(), "runtime-cache", "product-ops-service", "pod-01.json")
	original := ConfigResolveResponse{
		Scope: ConfigResolutionScope{
			Environment: "beta",
			Cluster:     "beta-control-a",
			Service:     "product-ops-service",
		},
		ResolvedAt:    "2026-05-18T01:00:00Z",
		EffectiveHash: "eff-hash",
		DesiredHash:   "des-hash",
		Values: []ResolvedConfigValue{
			{
				Key:        "sys.config_center.poll_interval_sec",
				Value:      45.0,
				ScopeLevel: "service",
				ScopeID:    "product-ops-service",
			},
		},
		Source: "config-center",
	}

	if err := SaveResolveSnapshot(path, original); err != nil {
		t.Fatalf("save snapshot: %v", err)
	}

	got, err := LoadResolveSnapshot(path)
	if err != nil {
		t.Fatalf("load snapshot: %v", err)
	}

	if !reflect.DeepEqual(got, original) {
		t.Fatalf("round trip mismatch:\nwant: %#v\ngot:  %#v", original, got)
	}
}
