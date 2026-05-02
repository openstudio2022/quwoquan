package application

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/application/skill"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type SkillSelection struct {
	SkillID      string
	DomainID     string
	DisplayName  string
	ToolPolicy   []string
	PromptPolicy string
}

type SkillRuntime interface {
	SelectSkill(ctx context.Context, turn assistant.AssistantTurn) (SkillSelection, error)
}

type DefaultSkillRuntime struct{}

func (DefaultSkillRuntime) SelectSkill(_ context.Context, turn assistant.AssistantTurn) (SkillSelection, error) {
	if IsP0ProactiveSkill(turn.SkillID) {
		domainID := strings.TrimSpace(turn.DomainID)
		if domainID == "" {
			domainID = "assistant"
		}
		return SkillSelection{
			SkillID:      turn.SkillID,
			DomainID:     domainID,
			DisplayName:  displaySkillName(turn.SkillID),
			ToolPolicy:   p0SkillToolPolicy(turn.SkillID),
			PromptPolicy: "m9." + turn.SkillID + ".proactive",
		}, nil
	}
	return ManifestSkillRuntime{
		Loader: assistantDomainSkillCatalogLoader{},
	}.SelectSkill(context.Background(), turn)
}

type ModelDrivenSkillRuntime struct {
	Model    ModelProvider
	Loader   skillpkg.Loader
	Fallback SkillRuntime
}

func (r ModelDrivenSkillRuntime) SelectSkill(ctx context.Context, turn assistant.AssistantTurn) (SkillSelection, error) {
	loader := r.Loader
	if loader == nil {
		loader = assistantDomainSkillCatalogLoader{}
	}
	catalog, err := loader.Load()
	if err != nil {
		return SkillSelection{}, err
	}
	if IsP0ProactiveSkill(turn.SkillID) {
		return DefaultSkillRuntime{}.SelectSkill(ctx, turn)
	}
	model := r.Model
	if model != nil && strings.TrimSpace(turn.Input.Text) != "" {
		resp, err := model.Complete(ctx, ModelRequest{
			TurnID:       turn.TurnID,
			TraceID:      turn.TraceID,
			Stage:        "skill_selection",
			Prompt:       buildSkillSelectionPrompt(catalog),
			UserQuestion: turn.Input.Text,
			SkillCatalog: catalog,
		})
		if err == nil {
			if manifest, ok := manifestByModelSelection(catalog, resp); ok {
				log.Printf("assistant skill selector model_selected turnId=%s skillId=%s reason=%s", turn.TurnID, manifest.SkillID, strings.TrimSpace(fmtAny(resp.StructuredDelta["reason"])))
				return selectionFromManifest(manifest), nil
			}
			log.Printf("assistant skill selector model_unmatched turnId=%s text=%q", turn.TurnID, resp.Text)
		} else {
			log.Printf("assistant skill selector model_failed turnId=%s err=%v", turn.TurnID, err)
		}
	}
	fallback := r.Fallback
	if fallback == nil {
		fallback = ManifestSkillRuntime{Loader: skillpkg.StaticLoader{Manifests: catalog}}
	}
	selection, err := fallback.SelectSkill(ctx, turn)
	if err == nil {
		log.Printf("assistant skill selector degraded_fallback turnId=%s skillId=%s", turn.TurnID, selection.SkillID)
	}
	return selection, err
}

func p0SkillToolPolicy(skillID string) []string {
	switch skillID {
	case SkillDailyAssistant:
		return []string{"app_search"}
	case SkillNewsBriefing:
		return []string{"web_search"}
	case SkillStockSentinel:
		return []string{"web_search"}
	case SkillTravelJourneyManager:
		return []string{"web_search", "app_search"}
	default:
		return []string{"mock_search"}
	}
}

type ManifestSkillRuntime struct {
	Loader skillpkg.Loader
}

func (r ManifestSkillRuntime) SelectSkill(_ context.Context, turn assistant.AssistantTurn) (SkillSelection, error) {
	loader := r.Loader
	if loader == nil {
		loader = skillpkg.StaticLoader{}
	}
	catalog, err := loader.Load()
	if err != nil {
		return SkillSelection{}, err
	}
	manifest := skillpkg.NewRouter(catalog).Route(turn)
	toolPolicy := manifest.ToolPolicy.PreferredTools
	if len(toolPolicy) == 0 {
		toolPolicy = manifest.ToolPolicy.AllowedTools
	}
	return SkillSelection{
		SkillID:      manifest.SkillID,
		DomainID:     manifest.DomainID,
		DisplayName:  manifest.DisplayName,
		ToolPolicy:   append([]string{}, toolPolicy...),
		PromptPolicy: "m5." + manifest.SkillID + ".reactive",
	}, nil
}

func selectionFromManifest(manifest skillpkg.Manifest) SkillSelection {
	toolPolicy := manifest.ToolPolicy.PreferredTools
	if len(toolPolicy) == 0 {
		toolPolicy = manifest.ToolPolicy.AllowedTools
	}
	return SkillSelection{
		SkillID:      manifest.SkillID,
		DomainID:     manifest.DomainID,
		DisplayName:  manifest.DisplayName,
		ToolPolicy:   append([]string{}, toolPolicy...),
		PromptPolicy: "m5." + manifest.SkillID + ".reactive",
	}
}

func manifestByModelSelection(catalog []skillpkg.Manifest, resp ModelResponse) (skillpkg.Manifest, bool) {
	skillID := strings.TrimSpace(fmtAny(resp.StructuredDelta["skillId"]))
	if skillID == "" && strings.TrimSpace(resp.Text) != "" {
		var parsed map[string]any
		if err := json.Unmarshal([]byte(resp.Text), &parsed); err == nil {
			skillID = strings.TrimSpace(fmtAny(parsed["skillId"]))
		}
	}
	if skillID == "" {
		return skillpkg.Manifest{}, false
	}
	for _, manifest := range catalog {
		if manifest.SkillID == skillID {
			return manifest, true
		}
	}
	return skillpkg.Manifest{}, false
}

func buildSkillSelectionPrompt(catalog []skillpkg.Manifest) string {
	var b strings.Builder
	b.WriteString("Select one assistant skillId from manifests for the user query. Return JSON only: {\"skillId\":\"...\",\"reason\":\"...\"}.\n")
	for _, manifest := range catalog {
		b.WriteString("- ")
		b.WriteString(manifest.SkillID)
		b.WriteString(": ")
		b.WriteString(manifest.DisplayName)
		if strings.TrimSpace(manifest.Description) != "" {
			b.WriteString(" — ")
			b.WriteString(manifest.Description)
		}
		b.WriteString("\n")
	}
	return b.String()
}

func fmtAny(value any) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(value))
}
