package post

import (
	"context"
	"errors"
	"strings"
)

// AssociationKind 是 canonical PostAssociationKind 的领域闭集。
type AssociationKind string

const (
	AssociationTopic      AssociationKind = "topic"
	AssociationNewsEvent  AssociationKind = "news_event"
	AssociationPlace      AssociationKind = "place"
	AssociationGathering  AssociationKind = "gathering"
	AssociationCollection AssociationKind = "collection"
)

type AssociationReference struct {
	Kind     AssociationKind
	TargetID string
}
type AssociationSummary struct {
	Kind     AssociationKind `json:"kind"`
	TargetID string          `json:"targetId"`
	Title    string          `json:"title"`
}

// AssociationTargetReader 由 owning tag/Homepage/Gathering/Collection 查询适配器实现。
// Gathering reader 必须同时验证作者参与事实与 viewer 目标可见性。
type AssociationTargetReader interface {
	ReadAssociation(context.Context, string, string, string) (AssociationSummary, bool, error)
}
type AssociationProjector struct {
	Tags        AssociationTargetReader
	Places      AssociationTargetReader
	Gatherings  AssociationTargetReader
	Collections AssociationTargetReader
}

func (p AssociationProjector) Project(ctx context.Context, author, viewer string, refs []AssociationReference) ([]AssociationSummary, error) {
	result := make([]AssociationSummary, 0, len(refs))
	seen := map[AssociationReference]bool{}
	for _, ref := range refs {
		if strings.TrimSpace(ref.TargetID) == "" {
			return nil, errors.New("association canonical identity missing")
		}
		if seen[ref] {
			continue
		}
		seen[ref] = true
		var reader AssociationTargetReader
		switch ref.Kind {
		case AssociationTopic, AssociationNewsEvent:
			reader = p.Tags
		case AssociationPlace:
			reader = p.Places
		case AssociationGathering:
			reader = p.Gatherings
		case AssociationCollection:
			reader = p.Collections
		default:
			return nil, errors.New("unknown association kind")
		}
		if reader == nil {
			return nil, errors.New("association owner reader unavailable")
		}
		summary, visible, err := reader.ReadAssociation(ctx, ref.TargetID, author, viewer)
		if err != nil {
			return nil, err
		}
		if !visible {
			continue
		}
		if summary.Kind != ref.Kind || summary.TargetID != ref.TargetID || strings.TrimSpace(summary.Title) == "" {
			return nil, errors.New("association owner returned mismatched identity")
		}
		result = append(result, summary)
	}
	return result, nil
}
