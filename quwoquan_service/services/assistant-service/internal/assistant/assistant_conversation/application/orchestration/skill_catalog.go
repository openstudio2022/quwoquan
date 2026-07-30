package orchestration

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"unicode"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
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

var (
	assistantSkillIndexMu   sync.RWMutex
	assistantSkillIndexRoot string
	assistantSkillIndex     map[string]skillpkg.Manifest
)

// assistantDomainSkillManifest 提供常驻的技能清单索引。清单体积小且不含话术正文，可以一直
// 驻留；话术正文由 PromptAssetResolver 在技能被选中时才加载。索引按资源根缓存，资源根变化时
// 重建，避免不同资源根之间互相污染。
func assistantDomainSkillManifest(skillID string) (skillpkg.Manifest, bool, error) {
	root, err := assistantSkillResourceRoot()
	if err != nil {
		return skillpkg.Manifest{}, false, err
	}
	assistantSkillIndexMu.RLock()
	index, ok := assistantSkillIndex, assistantSkillIndexRoot == root
	assistantSkillIndexMu.RUnlock()
	if !ok || index == nil {
		catalog, err := LoadAssistantDomainSkillCatalog()
		if err != nil {
			return skillpkg.Manifest{}, false, err
		}
		index = make(map[string]skillpkg.Manifest, len(catalog))
		for _, manifest := range catalog {
			index[manifest.SkillID] = manifest
		}
		assistantSkillIndexMu.Lock()
		assistantSkillIndex = index
		assistantSkillIndexRoot = root
		assistantSkillIndexMu.Unlock()
	}
	manifest, found := index[strings.TrimSpace(skillID)]
	return manifest, found, nil
}

// proactiveSkillManifest 返回主动订阅技能的清单。主动技能与反应式技能共用同一份清单目录，
// 代码里不再维护第二份主动技能名单与工具策略。
func proactiveSkillManifest(skillID string) (skillpkg.Manifest, bool) {
	manifest, found, err := assistantDomainSkillManifest(skillID)
	if err != nil {
		log.Printf("assistant skill catalog unavailable skillId=%s err=%v", skillID, err)
		return skillpkg.Manifest{}, false
	}
	if !found || !manifest.IsProactive() {
		return skillpkg.Manifest{}, false
	}
	return manifest, true
}

func AssistantDomainSkillCatalog() []skillpkg.Manifest {
	catalog, err := LoadAssistantDomainSkillCatalog()
	if err != nil {
		panic(fmt.Sprintf("load assistant domain skill catalog: %v", err))
	}
	return catalog
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
			filepath.Dir(file), "..", "..", "..", "..", "..",
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
		manifest.ProblemClass = strings.TrimSpace(manifest.ProblemClass)
		manifest.Activation = strings.TrimSpace(manifest.Activation)
		if manifest.Activation == "" {
			manifest.Activation = skillpkg.ActivationReactive
		}
		if manifest.Activation != skillpkg.ActivationReactive &&
			manifest.Activation != skillpkg.ActivationProactive {
			return nil, fmt.Errorf(
				"assistant domain skill %q declares unknown activation %q",
				manifest.SkillID,
				manifest.Activation,
			)
		}
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
		if err := validateSkillToolPolicy(manifest); err != nil {
			return nil, err
		}
		slotSchema, err := normalizeSkillSlotSchema(manifest.SkillID, manifest.SlotSchema)
		if err != nil {
			return nil, err
		}
		manifest.SlotSchema = slotSchema
		if _, err := assistantgenerated.ParseProblemClass(manifest.ProblemClass); err != nil {
			return nil, fmt.Errorf(
				"assistant domain skill %q declares unknown problemClass %q",
				manifest.SkillID,
				manifest.ProblemClass,
			)
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

func normalizeSkillSlotSchema(
	skillID string,
	schema skillpkg.SlotSchema,
) (skillpkg.SlotSchema, error) {
	seen := map[string]bool{}
	normalize := func(kind string, values []string) ([]string, error) {
		out := make([]string, 0, len(values))
		for _, value := range values {
			value = strings.TrimSpace(value)
			if !validSlotID(value) {
				return nil, fmt.Errorf(
					"assistant domain skill %q declares invalid %s slot %q",
					skillID,
					kind,
					value,
				)
			}
			if seen[value] {
				return nil, fmt.Errorf(
					"assistant domain skill %q declares duplicate slot %q",
					skillID,
					value,
				)
			}
			seen[value] = true
			out = append(out, value)
		}
		return out, nil
	}
	required, err := normalize("required", schema.RequiredSlots)
	if err != nil {
		return skillpkg.SlotSchema{}, err
	}
	optional, err := normalize("optional", schema.OptionalSlots)
	if err != nil {
		return skillpkg.SlotSchema{}, err
	}
	if len(required)+len(optional) > 16 {
		return skillpkg.SlotSchema{}, fmt.Errorf(
			"assistant domain skill %q declares too many slots",
			skillID,
		)
	}
	schema.RequiredSlots = required
	schema.OptionalSlots = optional
	schema.StateID = strings.TrimSpace(schema.StateID)
	schema.NextStateID = strings.TrimSpace(schema.NextStateID)
	return schema, nil
}

func validSlotID(value string) bool {
	if value == "" || len([]rune(value)) > 64 {
		return false
	}
	for _, current := range value {
		if unicode.IsLower(current) || unicode.IsDigit(current) || current == '_' {
			continue
		}
		return false
	}
	return true
}

// validateSkillToolPolicy 保证 manifest 声明的工具名都能在装配目录里找到实现，且偏好集是
// 允许集的子集。否则模型会选中一个注册表里不存在的工具，把整轮回答变成工具失败。
func validateSkillToolPolicy(manifest skillpkg.Manifest) error {
	canonical := map[string]bool{}
	for _, name := range toolpkg.CanonicalToolNames() {
		canonical[name] = true
	}
	allowed := map[string]bool{}
	for _, name := range manifest.ToolPolicy.AllowedTools {
		if !canonical[name] {
			return fmt.Errorf(
				"assistant domain skill %q allows unregistered tool %q; registered tools are %v",
				manifest.SkillID,
				name,
				toolpkg.CanonicalToolNames(),
			)
		}
		allowed[name] = true
	}
	for _, name := range manifest.ToolPolicy.PreferredTools {
		if !allowed[name] {
			return fmt.Errorf(
				"assistant domain skill %q prefers tool %q outside its allowedTools",
				manifest.SkillID,
				name,
			)
		}
	}
	return nil
}
