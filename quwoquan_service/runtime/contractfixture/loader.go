package contractfixture

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
)

func LoadRepositoryJSON[T any](repositoryRelativePath string) (T, error) {
	var out T
	path, err := RepositoryPath(repositoryRelativePath)
	if err != nil {
		return out, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return out, fmt.Errorf("read repository fixture %s: %w", repositoryRelativePath, err)
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return out, fmt.Errorf("decode repository fixture %s: %w", repositoryRelativePath, err)
	}
	return out, nil
}

func RepositoryPath(repositoryRelativePath string) (string, error) {
	if filepath.IsAbs(repositoryRelativePath) || filepath.Clean(repositoryRelativePath) != repositoryRelativePath {
		return "", fmt.Errorf("repository fixture path must be a clean relative path: %s", repositoryRelativePath)
	}
	candidates := []string{
		repositoryRelativePath,
		filepath.Join("..", repositoryRelativePath),
		filepath.Join("..", "..", repositoryRelativePath),
		filepath.Join("..", "..", "..", repositoryRelativePath),
		filepath.Join("..", "..", "..", "..", repositoryRelativePath),
		filepath.Join("..", "..", "..", "..", "..", repositoryRelativePath),
	}
	if _, file, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Join(
			filepath.Dir(file),
			"..", "..", "..", repositoryRelativePath,
		))
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("repository fixture not found: %s", repositoryRelativePath)
}
