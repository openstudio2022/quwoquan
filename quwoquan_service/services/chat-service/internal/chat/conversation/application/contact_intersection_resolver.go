package application

import (
	"context"
	"strings"
)

type ContactIntersectionSummary struct {
	IntersectionID string
	EvidenceID     string
	SourceRef      string
	ObjectTypeRef  string
	ObjectID       string
	PrimaryText    string
	Dimension      string
}

type ContactIntersectionResolver interface {
	ListContactIntersections(
		ctx context.Context,
		viewerPersonaID string,
		contactPersonaID string,
		limit int,
	) ([]ContactIntersectionSummary, error)
}

type emptyContactIntersectionResolver struct{}

func (emptyContactIntersectionResolver) ListContactIntersections(
	context.Context,
	string,
	string,
	int,
) ([]ContactIntersectionSummary, error) {
	return nil, nil
}

func ContactIntersectionTexts(
	summaries []ContactIntersectionSummary,
) []string {
	texts := make([]string, 0, 2)
	seen := map[string]struct{}{}
	for _, summary := range summaries {
		text := strings.TrimSpace(summary.PrimaryText)
		if text == "" {
			continue
		}
		if _, exists := seen[text]; exists {
			continue
		}
		seen[text] = struct{}{}
		texts = append(texts, text)
		if len(texts) == 2 {
			break
		}
	}
	return texts
}
