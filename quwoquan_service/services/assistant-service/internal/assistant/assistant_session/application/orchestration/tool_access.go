package orchestration

import (
	"context"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

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
