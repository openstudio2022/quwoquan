package readiness

import (
	"os"
	"path/filepath"
	"testing"
)

func TestReadStableRegularFileRejectsSymlinkAndOversizeInput(t *testing.T) {
	root := t.TempDir()
	regular := filepath.Join(root, "bundle.json")
	if err := os.WriteFile(regular, []byte(`{"results":[]}`), 0o600); err != nil {
		t.Fatal(err)
	}
	data, err := ReadStableRegularFile(regular, 1024)
	if err != nil || string(data) != `{"results":[]}` {
		t.Fatalf("data=%q err=%v", data, err)
	}
	link := filepath.Join(root, "linked.json")
	if err := os.Symlink(regular, link); err != nil {
		t.Fatal(err)
	}
	if _, err := ReadStableRegularFile(link, 1024); err == nil {
		t.Fatal("symlink input unexpectedly accepted")
	}
	if _, err := ReadStableRegularFile(regular, 2); err == nil {
		t.Fatal("oversize input unexpectedly accepted")
	}
}
