package contextassembly

import (
	"strings"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
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
	return "assistant"
}

func (DefaultDomainRouter) IsZero() bool {
	return false
}
