package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestBuildRedisRouterProvidesRealtimeFallback(t *testing.T) {
	cfg := config{}
	cfg.Redis.General.Mode = "memory"

	router := buildRedisRouter(cfg)
	defer router.Close()

	ctx := context.Background()
	if err := router.Scene("realtime").Set(ctx, "sync:test", "ok", time.Minute); err != nil {
		t.Fatalf("realtime set: %v", err)
	}
	got, err := router.Scene("realtime").Get(ctx, "sync:test")
	if err != nil {
		t.Fatalf("realtime get: %v", err)
	}
	if got != "ok" {
		t.Fatalf("realtime get = %q, want %q", got, "ok")
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
	write("configs/user-service/default/config.yaml", "config:\n  version: v0\n")
	write("configs/user-service/gamma/config.yaml", "service:\n  http:\n    addr: ':18082'\n")
	release := "releases/config/user-service/v2026.07.21.0.yaml"
	write(release, "config:\n  version: v2026.07.21.0\n")

	if _, err := loadRuntimeConfig(
		"user-service",
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
		"user-service",
		"gamma",
		root,
		"v2026.07.21.0",
	); err == nil {
		t.Fatal("missing canonical release overlay must fail startup")
	}
	write(release, "config: [\n")
	if _, err := loadRuntimeConfig(
		"user-service",
		"gamma",
		root,
		"v2026.07.21.0",
	); err == nil {
		t.Fatal("malformed canonical release overlay must fail startup")
	}
}
