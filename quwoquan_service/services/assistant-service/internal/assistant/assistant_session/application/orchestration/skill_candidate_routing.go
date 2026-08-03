package orchestration

import (
	"context"
	"log"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

// routeCandidateSkill 在策略归因冻结前，从 active Skill package 路由一次并冻结身份。
// PolicyRelease 不再复制 Skill 候选集合或替换领域能力。
func (s *AssistantService) routeCandidateSkill(
	ctx context.Context,
	input assistant.CreateTurnInput,
) (string, string) {
	skillID := strings.TrimSpace(input.SkillID)
	domainID := strings.TrimSpace(input.DomainID)
	if skillID != "" {
		return skillID, domainID
	}
	if s.agentLoop == nil || s.agentLoop.Skills == nil {
		return skillID, domainID
	}
	if strings.TrimSpace(input.Input.Text) == "" {
		return skillID, domainID
	}
	candidateTurn := assistant.AssistantTurn{
		DomainID: domainID,
		Input:    input.Input,
	}
	selection, err := s.agentLoop.Skills.SelectSkill(ctx, candidateTurn)
	if err != nil {
		log.Printf("assistant skill candidate routing failed err=%v", err)
		return skillID, domainID
	}
	routedSkillID := strings.TrimSpace(selection.SkillID)
	if routedSkillID == "" {
		return skillID, domainID
	}
	routedDomainID := strings.TrimSpace(selection.DomainID)
	if routedDomainID == "" {
		routedDomainID = domainID
	}
	log.Printf(
		"assistant skill candidate routed skillId=%s domainId=%s",
		routedSkillID,
		routedDomainID,
	)
	return routedSkillID, routedDomainID
}
