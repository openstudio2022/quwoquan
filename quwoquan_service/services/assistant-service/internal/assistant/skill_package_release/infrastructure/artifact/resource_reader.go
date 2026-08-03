package artifact

import (
	"context"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

const (
	LocatorScheme = "skill-package"
	LocatorHost   = "official"
	maxAssetBytes = 4 << 20
)

// ResourceReader exposes only explicitly addressed immutable official package
// assets. It is not a generic file reader: absolute paths, traversal,
// symlinks, alternate schemes and oversized assets are rejected.
type ResourceReader struct {
	root string
}

func NewResourceReader(root string) (*ResourceReader, error) {
	root = strings.TrimSpace(root)
	if root == "" {
		return nil, fmt.Errorf("Skill package asset root is required")
	}
	absolute, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve Skill package asset root: %w", err)
	}
	resolved, err := filepath.EvalSymlinks(absolute)
	if err != nil {
		return nil, fmt.Errorf("resolve Skill package asset root symlinks: %w", err)
	}
	info, err := os.Stat(resolved)
	if err != nil || !info.IsDir() {
		return nil, fmt.Errorf("Skill package asset root is not a directory")
	}
	return &ResourceReader{root: resolved}, nil
}

func (reader *ResourceReader) ReadAsset(
	ctx context.Context,
	locator string,
) ([]byte, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	path, err := reader.resolve(locator)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", packagemodel.ErrAssetUnavailable, err)
	}
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("%w: open asset: %v", packagemodel.ErrAssetUnavailable, err)
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil || !info.Mode().IsRegular() || info.Size() > maxAssetBytes {
		return nil, fmt.Errorf("%w: asset is not a bounded regular file", packagemodel.ErrAssetUnavailable)
	}
	content, err := io.ReadAll(io.LimitReader(file, maxAssetBytes+1))
	if err != nil || len(content) > maxAssetBytes {
		return nil, fmt.Errorf("%w: read bounded asset", packagemodel.ErrAssetUnavailable)
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return content, nil
}

func (reader *ResourceReader) resolve(locator string) (string, error) {
	if reader == nil || reader.root == "" {
		return "", fmt.Errorf("asset reader is not configured")
	}
	parsed, err := url.Parse(strings.TrimSpace(locator))
	if err != nil || parsed.Scheme != LocatorScheme || parsed.Host != LocatorHost ||
		parsed.RawQuery != "" || parsed.Fragment != "" || parsed.User != nil {
		return "", fmt.Errorf("invalid official Skill package locator")
	}
	relative := strings.TrimPrefix(parsed.EscapedPath(), "/")
	decoded, err := url.PathUnescape(relative)
	if err != nil || decoded == "" || filepath.IsAbs(decoded) ||
		decoded != filepath.ToSlash(filepath.Clean(decoded)) ||
		strings.HasPrefix(decoded, "../") || decoded == ".." {
		return "", fmt.Errorf("invalid official Skill package asset path")
	}
	candidate := filepath.Join(reader.root, filepath.FromSlash(decoded))
	resolved, err := filepath.EvalSymlinks(candidate)
	if err != nil {
		return "", fmt.Errorf("resolve official Skill package asset: %w", err)
	}
	relativeToRoot, err := filepath.Rel(reader.root, resolved)
	if err != nil || relativeToRoot == ".." || strings.HasPrefix(relativeToRoot, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("official Skill package asset escapes root")
	}
	return resolved, nil
}
