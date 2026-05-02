package runtimemedia

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// WriteDerivedMediaFile 将派生媒体写入本地根目录，路径与 objectKey 对齐（使用正斜杠语义）。
func WriteDerivedMediaFile(localRoot, objectKey string, data []byte) error {
	root := strings.TrimSpace(localRoot)
	if root == "" {
		return fmt.Errorf("local media root is required")
	}
	key := strings.TrimSpace(objectKey)
	if key == "" {
		return fmt.Errorf("objectKey is required")
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
