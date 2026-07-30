package runtimemedia

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// WriteDerivedMediaFile materializes one canonical public slice below the
// configured local delivery root. It never accepts a private object key or an
// arbitrary relative filesystem path.
func WriteDerivedMediaFile(localRoot, publicSliceKey string, data []byte) error {
	root := strings.TrimSpace(localRoot)
	if root == "" {
		return fmt.Errorf("local media root is required")
	}
	key := normalizePublicSliceKey(publicSliceKey)
	_, versioned := publicSliceVersion(key)
	if key == "" || !versioned {
		return fmt.Errorf("canonical publicSliceKey is required")
	}
	full := filepath.Join(root, filepath.FromSlash(key))
	dir := filepath.Dir(full)
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("mkdir derived media %s: %w", dir, err)
	}
	tmp := full + ".tmp"
	if err := os.WriteFile(tmp, data, 0o644); err != nil {
		return fmt.Errorf("write temp derived media: %w", err)
	}
	if err := os.Rename(tmp, full); err != nil {
		_ = os.Remove(tmp)
		return fmt.Errorf("finalize derived media: %w", err)
	}
	return nil
}
