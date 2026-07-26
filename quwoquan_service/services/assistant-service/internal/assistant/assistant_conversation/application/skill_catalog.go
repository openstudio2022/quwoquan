package application

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

const (
	assistantSkillManifestFileName = "manifest.json"
)

type assistantDomainSkillCatalogLoader struct{}

func (assistantDomainSkillCatalogLoader) Load() ([]skillpkg.Manifest, error) {
	return LoadAssistantDomainSkillCatalog()
}

func LoadAssistantDomainSkillCatalog() ([]skillpkg.Manifest, error) {
	manifestPaths, err := discoverAssistantSkillManifestPaths()
	if err != nil {
		return nil, err
	}
	catalog := make([]skillpkg.Manifest, 0, len(manifestPaths))
	for _, manifestPath := range manifestPaths {
		raw, err := os.ReadFile(manifestPath)
		if err != nil {
			return nil, fmt.Errorf("read assistant skill manifest %s: %w", manifestPath, err)
		}
		var manifest skillpkg.Manifest
		err = json.Unmarshal(raw, &manifest)
		if err != nil {
			return nil, fmt.Errorf("decode assistant skill manifest %s: %w", manifestPath, err)
		}
		catalog = append(catalog, manifest)
	}
	return validateAssistantDomainSkillCatalog(catalog)
}

func AssistantDomainSkillCatalog() []skillpkg.Manifest {
	catalog, err := LoadAssistantDomainSkillCatalog()
	if err != nil {
		panic(fmt.Sprintf("load assistant domain skill catalog: %v", err))
	}
	return catalog
}

func assistantDomainSkillCatalogViews() ([]assistant.AssistantSkillCatalogItemView, error) {
	catalog, err := LoadAssistantDomainSkillCatalog()
	if err != nil {
		return nil, err
	}
	items := make([]assistant.AssistantSkillCatalogItemView, 0, len(catalog))
	for _, manifest := range catalog {
		iconHint := strings.TrimSpace(manifest.IconHint)
		if iconHint == "" {
			iconHint = "sparkles"
		}
		items = append(items, assistant.AssistantSkillCatalogItemView{
			SkillID:         manifest.SkillID,
			DisplayName:     manifest.DisplayName,
			Description:     manifest.Description,
			Category:        manifest.DomainID,
			RequiresConsent: false,
			IconHint:        iconHint,
		})
	}
	return items, nil
}

func discoverAssistantSkillManifestPaths() ([]string, error) {
	root, err := assistantSkillResourceRoot()
	if err != nil {
		return nil, err
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("read assistant skill manifest root: %w", err)
	}
	paths := []string{}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		paths = append(paths, filepath.Join(root, entry.Name(), assistantSkillManifestFileName))
	}
	sort.Strings(paths)
	return paths, nil
}

func assistantSkillResourceRoot() (string, error) {
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
			filepath.Dir(file), "..", "..", "..", "..",
			"resources", "skills", "assistant", "assistant_conversation",
		))
	}
	for _, candidate := range candidates {
		if info, err := os.Stat(candidate); err == nil && info.IsDir() {
			return candidate, nil
		}
	}
	return "", fmt.Errorf("assistant skill resource root not found")
}

func validateAssistantDomainSkillCatalog(catalog []skillpkg.Manifest) ([]skillpkg.Manifest, error) {
	if len(catalog) == 0 {
		return nil, fmt.Errorf("empty assistant domain skill catalog")
	}
	seen := map[string]bool{}
	out := make([]skillpkg.Manifest, 0, len(catalog))
	hasFallback := false
	for i, manifest := range catalog {
		manifest.SkillID = strings.TrimSpace(manifest.SkillID)
		manifest.DisplayName = strings.TrimSpace(manifest.DisplayName)
		manifest.Description = strings.TrimSpace(manifest.Description)
		manifest.DomainID = strings.TrimSpace(manifest.DomainID)
		manifest.ExecutionTarget = strings.TrimSpace(manifest.ExecutionTarget)
		manifest.IconHint = strings.TrimSpace(manifest.IconHint)
		if manifest.SkillID == "" {
			return nil, fmt.Errorf("assistant domain skill catalog item %d missing skillId", i)
		}
		if seen[manifest.SkillID] {
			return nil, fmt.Errorf("duplicate assistant domain skill %q", manifest.SkillID)
		}
		seen[manifest.SkillID] = true
		if manifest.DisplayName == "" || manifest.DomainID == "" || manifest.ExecutionTarget == "" {
			return nil, fmt.Errorf("assistant domain skill %q missing displayName/domainId/executionTarget", manifest.SkillID)
		}
		if len(manifest.ToolPolicy.AllowedTools) == 0 && len(manifest.ToolPolicy.PreferredTools) == 0 {
			return nil, fmt.Errorf("assistant domain skill %q missing tool policy", manifest.SkillID)
		}
		if manifest.SkillID == "fallback_general_search" {
			hasFallback = true
		}
		out = append(out, manifest)
	}
	if !hasFallback {
		return nil, fmt.Errorf("assistant domain skill catalog missing fallback_general_search")
	}
	return out, nil
}
