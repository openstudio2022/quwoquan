package resource

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
)

const manifestFileName = "manifest.json"

type CatalogSource struct{}

func NewCatalogSource() *CatalogSource {
	return &CatalogSource{}
}

type manifestProjection struct {
	SkillID     string `json:"skillId"`
	DisplayName string `json:"displayName"`
	Description string `json:"description,omitempty"`
	DomainID    string `json:"domainId"`
	IconHint    string `json:"iconHint,omitempty"`
}

func (source *CatalogSource) ListCatalogItems(
	ctx context.Context,
) ([]model.Item, error) {
	root, err := skillManifestRoot()
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("read skill catalog root: %w", err)
	}
	items := builtInCapabilityItems()
	hasFallback := false
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		manifestPath := filepath.Join(root, entry.Name(), manifestFileName)
		raw, err := os.ReadFile(manifestPath)
		if err != nil {
			return nil, fmt.Errorf("read skill catalog manifest %s: %w", manifestPath, err)
		}
		var manifest manifestProjection
		if err := json.Unmarshal(raw, &manifest); err != nil {
			return nil, fmt.Errorf("decode skill catalog manifest %s: %w", manifestPath, err)
		}
		manifest.SkillID = strings.TrimSpace(manifest.SkillID)
		manifest.DisplayName = strings.TrimSpace(manifest.DisplayName)
		manifest.Description = strings.TrimSpace(manifest.Description)
		manifest.DomainID = strings.TrimSpace(manifest.DomainID)
		manifest.IconHint = strings.TrimSpace(manifest.IconHint)
		if manifest.SkillID == "" || manifest.DisplayName == "" || manifest.DomainID == "" {
			return nil, fmt.Errorf(
				"skill catalog manifest %s missing skillId/displayName/domainId",
				manifestPath,
			)
		}
		if manifest.IconHint == "" {
			manifest.IconHint = "sparkles"
		}
		if manifest.SkillID == "fallback_general_search" {
			hasFallback = true
		}
		items = append(items, model.Item{
			SkillID:     manifest.SkillID,
			DisplayName: manifest.DisplayName,
			Description: manifest.Description,
			Category:    manifest.DomainID,
			IconHint:    manifest.IconHint,
		})
	}
	if !hasFallback {
		return nil, fmt.Errorf("skill catalog missing fallback_general_search")
	}
	seen := make(map[string]struct{}, len(items))
	for _, item := range items {
		if _, exists := seen[item.SkillID]; exists {
			return nil, fmt.Errorf("duplicate skill catalog item %q", item.SkillID)
		}
		seen[item.SkillID] = struct{}{}
	}
	sort.Slice(items, func(left, right int) bool {
		return items[left].SkillID < items[right].SkillID
	})
	return items, nil
}

func builtInCapabilityItems() []model.Item {
	return []model.Item{
		{
			SkillID:         model.PersonalContentAccessSkillID,
			DisplayName:     "个人内容访问",
			Description:     "允许助手在授权后读取用户个人内容用于回答与建议。",
			Category:        "permission",
			RequiresConsent: true,
			IconHint:        "lock_open",
		},
		{
			SkillID:     "assistant_learning",
			DisplayName: "学习反馈闭环",
			Description: "基于交互事件与评分卡形成在线学习与运营回看。",
			Category:    "analytics",
			IconHint:    "school",
		},
		{
			SkillID:     "assistant_navigation",
			DisplayName: "页面建议动作",
			Description: "根据当前 page context 返回可执行的建议动作。",
			Category:    "navigation",
			IconHint:    "bolt",
		},
	}
}

func skillManifestRoot() (string, error) {
	if configured := strings.TrimSpace(os.Getenv("ASSISTANT_RESOURCE_ROOT")); configured != "" {
		if info, err := os.Stat(configured); err == nil && info.IsDir() {
			return configured, nil
		}
		return "", fmt.Errorf("ASSISTANT_RESOURCE_ROOT is not a directory: %s", configured)
	}
	candidates := []string{
		filepath.Join("resources", "skills", "assistant", "assistant_conversation"),
		filepath.Join("quwoquan_service", "services", "assistant-service", "resources", "skills", "assistant", "assistant_conversation"),
		filepath.Join("services", "assistant-service", "resources", "skills", "assistant", "assistant_conversation"),
	}
	if _, file, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Join(
			filepath.Dir(file), "..", "..", "..", "..", "..",
			"resources", "skills", "assistant", "assistant_conversation",
		))
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("assistant skill catalog resource root not found")
}
