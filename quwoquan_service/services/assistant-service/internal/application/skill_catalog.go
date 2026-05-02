package application

import (
	"fmt"
	"os"
	"sort"
	"strings"

	"quwoquan_service/runtime/contractfixture"
	skillpkg "quwoquan_service/services/assistant-service/internal/application/skill"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

const (
	assistantSkillManifestRootMetadataPath = "assistant/skills"
	assistantSkillManifestFileName         = "manifest.json"
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
		manifest, err := contractfixture.LoadMetadataJSON[skillpkg.Manifest](manifestPath)
		if err != nil {
			return nil, err
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
	root, err := contractfixture.MetadataPath(assistantSkillManifestRootMetadataPath)
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
		paths = append(paths, assistantSkillManifestRootMetadataPath+"/"+entry.Name()+"/"+assistantSkillManifestFileName)
	}
	sort.Strings(paths)
	return paths, nil
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
