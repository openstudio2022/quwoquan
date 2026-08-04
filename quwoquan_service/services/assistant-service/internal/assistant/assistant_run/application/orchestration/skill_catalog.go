package orchestration

import (
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// ValidateAssistantDomainSkillCatalog validates already resolved immutable
// package assets. It performs no source discovery and never reads files.
func ValidateAssistantDomainSkillCatalog(catalog []skillpkg.Manifest) ([]skillpkg.Manifest, error) {
	if len(catalog) == 0 {
		return nil, fmt.Errorf("empty assistant domain skill catalog")
	}
	seen := map[string]bool{}
	out := make([]skillpkg.Manifest, 0, len(catalog))
	fallbackCount := 0
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
			manifest.Activation != skillpkg.ActivationProactive &&
			manifest.Activation != skillpkg.ActivationHybrid {
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
		if strings.TrimSpace(manifest.CatalogProfileRef) == "" ||
			strings.TrimSpace(manifest.ActivationProfileRef) == "" ||
			strings.TrimSpace(manifest.InputProfileRef) == "" ||
			strings.TrimSpace(manifest.ContextProfileRef) == "" ||
			strings.TrimSpace(manifest.CapabilityProfileRef) == "" ||
			strings.TrimSpace(manifest.OrchestrationProfileRef) == "" ||
			strings.TrimSpace(manifest.TriggerProfileRef) == "" ||
			strings.TrimSpace(manifest.MemoryProfileRef) == "" ||
			strings.TrimSpace(manifest.PresentationProfileRef) == "" ||
			strings.TrimSpace(manifest.EvaluationProfileRef) == "" ||
			strings.TrimSpace(manifest.ReplayAssetRef) == "" ||
			len(manifest.ResolvedAssetRefs) != 11 {
			return nil, fmt.Errorf("assistant domain skill %q has incomplete profile asset refs", manifest.SkillID)
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
		if manifest.RoutingFallback {
			if !manifest.IsReactive() {
				return nil, fmt.Errorf(
					"assistant domain skill %q declares routingFallback without reactive activation",
					manifest.SkillID,
				)
			}
			fallbackCount++
		}
		out = append(out, manifest)
	}
	if fallbackCount != 1 {
		return nil, fmt.Errorf(
			"assistant domain skill catalog must declare exactly one routingFallback, got %d",
			fallbackCount,
		)
	}
	return out, nil
}

func normalizeSkillSlotSchema(skillID string, schema skillpkg.SlotSchema) (skillpkg.SlotSchema, error) {
	normalized, err := skillpkg.NormalizeSlotSchema(schema)
	if err != nil {
		return skillpkg.SlotSchema{}, fmt.Errorf(
			"assistant domain skill %q has invalid slot schema: %w",
			skillID,
			err,
		)
	}
	return normalized, nil
}

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
			return fmt.Errorf("assistant domain skill %q prefers tool %q outside its allowedTools", manifest.SkillID, name)
		}
	}
	return nil
}
