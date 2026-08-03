package orchestration

import (
	"fmt"
	"strings"
	"unicode"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
)

// ValidateAssistantDomainSkillCatalog validates already resolved immutable
// package assets. It performs no source discovery and never reads files.
func ValidateAssistantDomainSkillCatalog(catalog []skillpkg.Manifest) ([]skillpkg.Manifest, error) {
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

func normalizeSkillSlotSchema(skillID string, schema skillpkg.SlotSchema) (skillpkg.SlotSchema, error) {
	seen := map[string]bool{}
	normalize := func(kind string, values []string) ([]string, error) {
		out := make([]string, 0, len(values))
		for _, value := range values {
			value = strings.TrimSpace(value)
			if !validSlotID(value) {
				return nil, fmt.Errorf("assistant domain skill %q declares invalid %s slot %q", skillID, kind, value)
			}
			if seen[value] {
				return nil, fmt.Errorf("assistant domain skill %q declares duplicate slot %q", skillID, value)
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
		return skillpkg.SlotSchema{}, fmt.Errorf("assistant domain skill %q declares too many slots", skillID)
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
