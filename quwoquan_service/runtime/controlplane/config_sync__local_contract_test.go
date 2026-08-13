package controlplane

import (
	"path/filepath"
	"testing"
)

func TestDefaultSnapshotPathUsesConfigRoot(t *testing.T) {
	got := defaultSnapshotPath("/etc/qwq-config", "product-ops-service", "pod-01")
	want := "/etc/qwq-config/runtime-cache/product-ops-service/pod-01.json"
	if got != want {
		t.Fatalf("expected %q, got %q", want, got)
	}
}

func TestDefaultSnapshotPathUsesOutputRoot(t *testing.T) {
	t.Setenv("QWQ_OUTPUT_ROOT", "/tmp/qwq-output")
	got := defaultSnapshotPath("", "product-ops-service", "pod-01")
	want := "/tmp/qwq-output/env/repo/local/control-plane/process/product-ops-service/pod-01.json"
	if got != want {
		t.Fatalf("expected %q, got %q", want, got)
	}
}

func TestDefaultSnapshotPathDoesNotUseRelativeOutputRoot(t *testing.T) {
	t.Setenv("QWQ_OUTPUT_ROOT", "")
	got := filepath.ToSlash(defaultSnapshotPath("", "product-ops-service", "pod-01"))
	if got == ".qwq_output/env/repo/local/control-plane/process/product-ops-service/pod-01.json" {
		t.Fatalf("snapshot path must not be relative to service cwd")
	}
}
