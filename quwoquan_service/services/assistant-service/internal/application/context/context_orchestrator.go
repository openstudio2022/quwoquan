package context

import (
	"context"
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type ClientContext struct {
	SurfaceID string         `json:"surfaceId,omitempty"`
	Locale    string         `json:"locale,omitempty"`
	Region    string         `json:"region,omitempty"`
	Values    map[string]any `json:"values,omitempty"`
}

type DeviceContextResponse struct {
	Status           string         `json:"status"`
	DeviceContextRef string         `json:"deviceContextRef,omitempty"`
	Facts            map[string]any `json:"facts,omitempty"`
	Reason           string         `json:"reason,omitempty"`
}

type AssemblyResult struct {
	Turn               assistant.AssistantTurn `json:"turn"`
	ClientContext      ClientContext           `json:"clientContext"`
	DeviceContext      DeviceContextResponse   `json:"deviceContext"`
	DomainID           string                  `json:"domainId"`
	RecallHints        []RecallHint            `json:"recallHints"`
	PromptVariables    map[string]string       `json:"promptVariables"`
	MissingContextKeys []string                `json:"missingContextKeys"`
}

type ContextOrchestrator struct {
	Recall RecallCoordinator
	Router DomainRouter
}

func (o ContextOrchestrator) Assemble(ctx context.Context, turn assistant.AssistantTurn, client ClientContext, device DeviceContextResponse) (AssemblyResult, error) {
	if err := ctx.Err(); err != nil {
		return AssemblyResult{}, err
	}
	router := o.Router
	if router == nil || router.IsZero() {
		router = DefaultDomainRouter{}
	}
	recall := o.Recall
	if recall.IsZero() {
		recall = NewRecallCoordinator(nil)
	}
	domainID := router.Route(turn, client)
	hints := recall.Recall(turn, domainID)
	result := AssemblyResult{
		Turn:          turn,
		ClientContext: client,
		DeviceContext: device,
		DomainID:      domainID,
		RecallHints:   hints,
		PromptVariables: map[string]string{
			"input_text": strings.TrimSpace(turn.Input.Text),
			"domain_id":  domainID,
			"surface_id": strings.TrimSpace(client.SurfaceID),
		},
	}
	if device.Status == "denied" || device.Status == "unavailable" || device.Status == "stale" {
		result.MissingContextKeys = append(result.MissingContextKeys, device.Status)
	}
	return result, nil
}
