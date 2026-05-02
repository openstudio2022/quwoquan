package context

import (
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type DomainRouter interface {
	Route(turn assistant.AssistantTurn, client ClientContext) string
	IsZero() bool
}

type DefaultDomainRouter struct{}

func (DefaultDomainRouter) Route(turn assistant.AssistantTurn, _ ClientContext) string {
	if domainID := strings.TrimSpace(turn.DomainID); domainID != "" {
		return domainID
	}
	if skillID := strings.TrimSpace(turn.SkillID); strings.Contains(skillID, ".") {
		return strings.SplitN(skillID, ".", 2)[0]
	}
	return "assistant"
}

func (DefaultDomainRouter) IsZero() bool {
	return false
}
