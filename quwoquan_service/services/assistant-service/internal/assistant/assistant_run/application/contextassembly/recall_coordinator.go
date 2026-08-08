package contextassembly

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"unicode"

	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

type RecallHint struct {
	HintID            string            `json:"hintId"`
	DomainID          string            `json:"domainId"`
	Text              string            `json:"text"`
	Score             float64           `json:"score"`
	Source            string            `json:"source"`
	Kind              string            `json:"kind,omitempty"`
	EvidenceIDs       []string          `json:"evidenceIds,omitempty"`
	SlotContributions map[string]string `json:"slotContributions,omitempty"`
}

type RecallRequest struct {
	Turn     assistant.AssistantTurn
	DomainID string
}

type RecallSource interface {
	Recall(context.Context, RecallRequest) ([]RecallHint, error)
}

type RecallCoordinator struct {
	Sources  []RecallSource
	MaxHints int
}

func NewRecallCoordinator(sources ...RecallSource) RecallCoordinator {
	return RecallCoordinator{Sources: append([]RecallSource(nil), sources...), MaxHints: 8}
}

func (r RecallCoordinator) IsZero() bool {
	return r.Sources == nil && r.MaxHints == 0
}

func (r RecallCoordinator) Recall(
	ctx context.Context,
	request RecallRequest,
) ([]RecallHint, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	sources := r.Sources
	if len(sources) == 0 {
		sources = []RecallSource{authorizedTurnRecallSource{}}
	}
	hints := make([]RecallHint, 0, 8)
	for _, source := range sources {
		if source == nil {
			continue
		}
		current, err := source.Recall(ctx, request)
		if err != nil {
			return nil, fmt.Errorf("recall source failed: %w", err)
		}
		hints = append(hints, current...)
	}
	sort.SliceStable(hints, func(i, j int) bool {
		return hints[i].Score > hints[j].Score
	})
	limit := r.MaxHints
	if limit <= 0 {
		limit = 8
	}
	if len(hints) > limit {
		hints = hints[:limit]
	}
	return hints, nil
}

type authorizedTurnRecallSource struct{}

func (authorizedTurnRecallSource) Recall(
	_ context.Context,
	request RecallRequest,
) ([]RecallHint, error) {
	turn := request.Turn
	queryTerms := recallTerms(turn.Input.Text)
	hints := make([]RecallHint, 0, len(turn.ContextTurns)+len(turn.IntersectionEvidence))
	for _, evidence := range turn.IntersectionEvidence {
		text := strings.TrimSpace(evidence.PrimaryText)
		if text == "" {
			continue
		}
		hints = append(hints, RecallHint{
			HintID:      evidence.EvidenceID,
			DomainID:    request.DomainID,
			Text:        text,
			Score:       recallScore(queryTerms, text, 0.90),
			Source:      "intersection",
			EvidenceIDs: []string{evidence.EvidenceID},
		})
	}
	if turn.ContextSummary != nil && strings.TrimSpace(turn.ContextSummary.Text) != "" {
		hints = append(hints, RecallHint{
			HintID:            turn.ContextSummary.SummaryID,
			DomainID:          request.DomainID,
			Text:              turn.ContextSummary.Text,
			Score:             recallScore(queryTerms, turn.ContextSummary.Text, 0.78),
			Source:            "session_summary",
			EvidenceIDs:       []string{turn.ContextSummary.SummaryID},
			SlotContributions: copyStringMap(turn.ContextSummary.ConfirmedSlots),
		})
	}
	if turn.PageContext != nil {
		for index, object := range turn.PageContext.PageObjects {
			text := strings.TrimSpace(object.ObjectTypeRef) + ":" + strings.TrimSpace(object.ObjectID)
			hints = append(hints, RecallHint{
				HintID:   fmt.Sprintf("%s:page:%d", turn.TurnID, index),
				DomainID: request.DomainID,
				Text:     text,
				Score:    recallScore(queryTerms, text, 0.72),
				Source:   "page_object",
			})
		}
	}
	for index := len(turn.ContextTurns) - 1; index >= 0; index-- {
		item := turn.ContextTurns[index]
		text := strings.TrimSpace(item.Text)
		if text == "" {
			continue
		}
		recency := float64(index+1) / float64(len(turn.ContextTurns)+1)
		hints = append(hints, RecallHint{
			HintID:   fmt.Sprintf("%s:session:%d", turn.TurnID, index),
			DomainID: request.DomainID,
			Text:     text,
			Score:    recallScore(queryTerms, text, 0.45+0.25*recency),
			Source:   "session_" + strings.TrimSpace(item.Role),
		})
	}
	return hints, nil
}

func copyStringMap(source map[string]string) map[string]string {
	if len(source) == 0 {
		return nil
	}
	out := make(map[string]string, len(source))
	for key, value := range source {
		out[key] = value
	}
	return out
}

func recallScore(queryTerms map[rune]struct{}, candidate string, base float64) float64 {
	candidateTerms := recallTerms(candidate)
	if len(queryTerms) == 0 || len(candidateTerms) == 0 {
		return base
	}
	overlap := 0
	for term := range candidateTerms {
		if _, ok := queryTerms[term]; ok {
			overlap++
		}
	}
	return base + 0.09*float64(overlap)/float64(len(candidateTerms))
}

func recallTerms(text string) map[rune]struct{} {
	terms := map[rune]struct{}{}
	for _, current := range strings.ToLower(strings.TrimSpace(text)) {
		if unicode.IsLetter(current) || unicode.IsDigit(current) {
			terms[current] = struct{}{}
		}
	}
	return terms
}
