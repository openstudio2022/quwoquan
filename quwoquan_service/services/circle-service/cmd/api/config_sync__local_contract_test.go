package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestDefaultClusterNamePerEnvironment(t *testing.T) {
	cases := []struct {
		env  string
		want string
	}{
		{env: "alpha", want: "alpha-control-a"},
		{env: "beta", want: "beta-control-a"},
		{env: "gamma", want: "gamma-control-a"},
		{env: "prod", want: "prod-control-a"},
	}
	for _, tc := range cases {
		if got := defaultClusterName(tc.env); got != tc.want {
			t.Fatalf("defaultClusterName(%q) = %q, want %q", tc.env, got, tc.want)
		}
	}
}

func TestLoadRuntimeConfig_ExternalReleaseOverlayIsRequired(t *testing.T) {
	root := t.TempDir()
	write := func(relative, content string) {
		t.Helper()
		path := filepath.Join(root, relative)
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("mkdir %s: %v", path, err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatalf("write %s: %v", path, err)
		}
	}
	write("configs/circle-service/default/config.yaml", "config:\n  version: v0\n")
	write("configs/circle-service/gamma/config.yaml", "service:\n  http:\n    addr: ':18091'\n")
	release := "releases/config/circle-service/v2026.07.21.0.yaml"
	write(release, "config:\n  version: v2026.07.21.0\n")

	if _, err := loadRuntimeConfig(
		"circle-service",
		"gamma",
		root,
		"v2026.07.21.0",
	); err != nil {
		t.Fatalf("load canonical external release config: %v", err)
	}
	if err := os.Remove(filepath.Join(root, release)); err != nil {
		t.Fatalf("remove release overlay: %v", err)
	}
	if _, err := loadRuntimeConfig(
		"circle-service",
		"gamma",
		root,
		"v2026.07.21.0",
	); err == nil {
		t.Fatal("missing canonical release overlay must fail startup")
	}
}
