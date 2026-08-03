// Package assets contains the build-time/test source reader for Skill prompt
// assets. Production execution resolves prompt bodies only from the immutable
// SkillPackageRelease frozen by AssistantRun.
package assets

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
)

const promptAssetFileExtension = ".md"

// PromptAssetLoader 从资产目录按 ID 读取提示词正文。ID 只允许出现字母、数字、点、下划线
// 与短横线，杜绝通过 ID 逃逸出资产目录。
type PromptAssetLoader struct {
	Root string

	mu     sync.RWMutex
	loaded map[string]string
}

func NewPromptAssetLoader(root string) *PromptAssetLoader {
	return &PromptAssetLoader{Root: strings.TrimSpace(root)}
}

// NewDefaultPromptAssetLoader 按仓库约定定位资产目录，供组合根与测试共用一份寻址逻辑。
func NewDefaultPromptAssetLoader() (*PromptAssetLoader, error) {
	root, err := DefaultPromptAssetRoot()
	if err != nil {
		return nil, err
	}
	return NewPromptAssetLoader(root), nil
}

// DefaultPromptAssetRoot 解析技能拥有的提示词资产目录。ASSISTANT_PROMPT_ASSET_ROOT
// 优先，其次按运行目录与源码位置逐个尝试仓库内的 canonical skills 路径。
func DefaultPromptAssetRoot() (string, error) {
	if configured := strings.TrimSpace(os.Getenv("ASSISTANT_PROMPT_ASSET_ROOT")); configured != "" {
		if info, err := os.Stat(configured); err == nil && info.IsDir() {
			return configured, nil
		}
		return "", fmt.Errorf("ASSISTANT_PROMPT_ASSET_ROOT is not a directory: %s", configured)
	}
	relative := filepath.Join("resources", "skills", "assistant", "assistant_session")
	candidates := []string{
		relative,
		filepath.Join("quwoquan_service", "services", "assistant-service", relative),
		filepath.Join("services", "assistant-service", relative),
	}
	if _, file, _, ok := runtime.Caller(0); ok {
		candidates = append(
			candidates,
			filepath.Join(filepath.Dir(file), "..", "..", "..", "..", "..", relative),
		)
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("assistant prompt asset root not found")
}

func (l *PromptAssetLoader) ResolvePromptAssets(
	_ context.Context,
	assetIDs []string,
) (string, error) {
	sections := make([]string, 0, len(assetIDs))
	for _, assetID := range assetIDs {
		content, err := l.load(assetID)
		if err != nil {
			return "", err
		}
		sections = append(sections, content)
	}
	return strings.Join(sections, "\n\n"), nil
}

func (l *PromptAssetLoader) load(assetID string) (string, error) {
	assetID = strings.TrimSpace(assetID)
	if err := validateAssetID(assetID); err != nil {
		return "", err
	}
	l.mu.RLock()
	cached, ok := l.loaded[assetID]
	l.mu.RUnlock()
	if ok {
		return cached, nil
	}
	if l.Root == "" {
		return "", fmt.Errorf("prompt asset root is not configured")
	}
	raw, err := os.ReadFile(filepath.Join(l.Root, assetID+promptAssetFileExtension))
	if err != nil {
		return "", fmt.Errorf("read prompt asset %q: %w", assetID, err)
	}
	content := strings.TrimSpace(string(raw))
	if content == "" {
		return "", fmt.Errorf("prompt asset %q is empty", assetID)
	}
	l.mu.Lock()
	if l.loaded == nil {
		l.loaded = map[string]string{}
	}
	l.loaded[assetID] = content
	l.mu.Unlock()
	return content, nil
}

func validateAssetID(assetID string) error {
	if assetID == "" {
		return fmt.Errorf("prompt asset id is required")
	}
	for _, r := range assetID {
		switch {
		case r >= 'a' && r <= 'z',
			r >= 'A' && r <= 'Z',
			r >= '0' && r <= '9',
			r == '.', r == '_', r == '-':
		default:
			return fmt.Errorf("prompt asset id %q contains unsupported character %q", assetID, r)
		}
	}
	return nil
}
