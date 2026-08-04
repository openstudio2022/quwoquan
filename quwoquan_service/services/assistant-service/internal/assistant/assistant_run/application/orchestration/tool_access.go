package orchestration

import (
	"context"

	react "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/reasoning"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

func (l *AgentLoop) prePlanAccess() func(
	context.Context,
	assistant.AssistantTurn,
	SkillSelection,
) error {
	if l == nil || l.SkillAccess == nil {
		return nil
	}
	return func(
		ctx context.Context,
		turn assistant.AssistantTurn,
		skill SkillSelection,
	) error {
		return l.SkillAccess.AuthorizeSkill(ctx, turn, skill.SkillID)
	}
}

func (l *AgentLoop) preToolUse() func(
	context.Context,
	assistant.AssistantTurn,
	SkillSelection,
	string,
	toolpkg.Metadata,
) error {
	if l == nil || (l.SkillAccess == nil && l.ToolAccess == nil) {
		return nil
	}
	return func(
		ctx context.Context,
		turn assistant.AssistantTurn,
		skill SkillSelection,
		toolName string,
		metadata toolpkg.Metadata,
	) error {
		if l.SkillAccess != nil {
			if err := l.SkillAccess.AuthorizeSkill(ctx, turn, skill.SkillID); err != nil {
				return err
			}
		}
		if l.ToolAccess != nil {
			return l.ToolAccess.AuthorizeTool(
				ctx,
				turn,
				skill,
				toolName,
				metadata,
			)
		}
		return nil
	}
}

func authorizedModelToolCatalog(
	ctx context.Context,
	turn assistant.AssistantTurn,
	skill SkillSelection,
	declared []ports.ModelToolDefinition,
	metadata map[string]toolpkg.Metadata,
	guard react.ToolExecutionGuard,
	authorize func(
		context.Context,
		assistant.AssistantTurn,
		SkillSelection,
		string,
		toolpkg.Metadata,
	) error,
) ([]ports.ModelToolDefinition, []string) {
	visible := make([]ports.ModelToolDefinition, 0, len(declared))
	allowed := make([]string, 0, len(declared))
	for _, definition := range declared {
		name := definition.Name
		frozen, found := metadata[name]
		if !found || guard.Allow(name) != nil {
			continue
		}
		if authorize != nil && authorize(ctx, turn, skill, name, frozen) != nil {
			continue
		}
		visible = append(visible, definition)
		allowed = append(allowed, name)
	}
	return visible, allowed
}
