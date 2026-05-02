package contractfixture

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

func LoadMetadataJSON[T any](metadataRelativePath string) (T, error) {
	var out T
	path, err := MetadataPath(metadataRelativePath)
	if err != nil {
		return out, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return out, fmt.Errorf("read metadata fixture %s: %w", metadataRelativePath, err)
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return out, fmt.Errorf("decode metadata fixture %s: %w", metadataRelativePath, err)
	}
	return out, nil
}

func MetadataPath(metadataRelativePath string) (string, error) {
	candidates := []string{
		filepath.Join("contracts", "metadata", metadataRelativePath),
		filepath.Join("quwoquan_service", "contracts", "metadata", metadataRelativePath),
		filepath.Join("..", "contracts", "metadata", metadataRelativePath),
		filepath.Join("..", "..", "contracts", "metadata", metadataRelativePath),
		filepath.Join("..", "..", "..", "contracts", "metadata", metadataRelativePath),
		filepath.Join("..", "..", "..", "..", "contracts", "metadata", metadataRelativePath),
	}
	if _, file, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Join(
			filepath.Dir(file),
			"..", "..",
			"contracts", "metadata", metadataRelativePath,
		))
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("metadata fixture not found: %s", metadataRelativePath)
}
