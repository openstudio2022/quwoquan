package context

import "quwoquan_service/services/assistant-service/internal/domain/assistant"

type RecallHint struct {
	HintID   string  `json:"hintId"`
	DomainID string  `json:"domainId"`
	Text     string  `json:"text"`
	Score    float64 `json:"score"`
}

type RecallCoordinator struct {
	Seed []RecallHint
}

func NewRecallCoordinator(seed []RecallHint) RecallCoordinator {
	return RecallCoordinator{Seed: append([]RecallHint{}, seed...)}
}

func (r RecallCoordinator) IsZero() bool {
	return r.Seed == nil
}

func (r RecallCoordinator) Recall(turn assistant.AssistantTurn, domainID string) []RecallHint {
	if len(r.Seed) > 0 {
		return append([]RecallHint{}, r.Seed...)
	}
	if turn.Input.Text == "" {
		return []RecallHint{}
	}
	return []RecallHint{{
		HintID:   turn.TurnID + ":recall:input",
		DomainID: domainID,
		Text:     turn.Input.Text,
		Score:    1,
	}}
}
