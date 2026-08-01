package orchestration

import (
	"context"
	"log"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

// routeCandidateSkill 在冻结策略之前给出候选技能。策略发布仍是允许集合与模板的唯一
// 决定者：这里只把"用户这句话属于哪个垂类"作为路由输入交给策略，策略据此挑选模板；
// 无法判断时返回空值，策略回落到默认模板。
//
// 路由必须发生在冻结之前，冻结结果才能同时作为回放依据与观测归因；一次运行只路由一次。
func (s *AssistantService) routeCandidateSkill(
	ctx context.Context,
	input assistant.CreateTurnInput,
	policyID string,
	personaID string,
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
	selection, err := s.selectSkillWithinPolicy(ctx, candidateTurn, policyID, personaID)
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

// selectSkillWithinPolicy 先问策略"这一人群能服务哪些技能"，再让技能运行时在集合内选择。
// 拿不到集合或运行时不支持集合选择时退回全目录选择，并记录退回原因。
func (s *AssistantService) selectSkillWithinPolicy(
	ctx context.Context,
	turn assistant.AssistantTurn,
	policyID string,
	personaID string,
) (SkillSelection, error) {
	scoped, ok := s.agentLoop.Skills.(ScopedSkillRuntime)
	if !ok {
		return s.agentLoop.Skills.SelectSkill(ctx, turn)
	}
	candidates := s.policySkillCandidateIDs(ctx, policyID, personaID)
	return scoped.SelectSkillWithin(ctx, turn, candidates)
}

func (s *AssistantService) policySkillCandidateIDs(
	ctx context.Context,
	policyID string,
	personaID string,
) []string {
	if s.policySkillCandidates == nil {
		return nil
	}
	policyID = strings.TrimSpace(policyID)
	personaID = strings.TrimSpace(personaID)
	if policyID == "" || personaID == "" {
		return nil
	}
	candidates, err := s.policySkillCandidates.ResolvePolicySkillCandidates(ctx, policyID, personaID)
	if err != nil {
		log.Printf(
			"assistant policy skill candidates unavailable policyId=%s err=%v",
			policyID,
			err,
		)
		return nil
	}
	return candidates
}
