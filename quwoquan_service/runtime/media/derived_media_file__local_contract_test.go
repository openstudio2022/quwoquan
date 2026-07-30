package runtimemedia

import (
	"os"
	"path/filepath"
	"testing"
)

func TestWriteDerivedMediaFileUsesCanonicalPublicSlicePath(t *testing.T) {
	root := t.TempDir()
	key := "media/avatar/s/conversation/conversation_001/v1/avatar.png"
	want := []byte("png")

	if err := WriteDerivedMediaFile(root, key, want); err != nil {
		t.Fatalf("write canonical public slice: %v", err)
	}
	got, err := os.ReadFile(filepath.Join(root, filepath.FromSlash(key)))
	if err != nil {
		t.Fatalf("read materialized public slice: %v", err)
	}
	if string(got) != string(want) {
		t.Fatalf("unexpected materialized bytes %q", got)
	}
}

func TestWriteDerivedMediaFileRejectsNonCanonicalOrUnversionedPath(t *testing.T) {
	root := t.TempDir()
	for _, key := range []string{
		"../../outside.png",
		"media/avatar/s/conversation/conversation_001/avatar.png",
		"media/objects/sha256/aa/hash",
	} {
		if err := WriteDerivedMediaFile(root, key, []byte("x")); err == nil {
			t.Fatalf("expected public slice rejection for %q", key)
		}
	}
}
