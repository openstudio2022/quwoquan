package application

import (
	"context"
	"strings"
)

type ContactIntersectionSummary struct {
	IntersectionID    string
	EvidenceID        string
	SourceRef         string
	ObjectTypeRef     string
	ObjectID          string
	PrimaryText       string
	Dimension         string
	IntersectionClass string
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

// ContactIntersectionFacts 把云侧交集摘要收敛为联系首页/会话头的 typed wire 事实
// （contracts/chat/conversation 的 ContactIntersectionFact，≤2 条）。
// 主句缺失或重复的条目整条丢弃：Chat 不拼句、不造依据（REQ-001/REQ-004）。
func ContactIntersectionFacts(
	summaries []ContactIntersectionSummary,
) []map[string]any {
	facts := make([]map[string]any, 0, 2)
	seen := map[string]struct{}{}
	for _, summary := range summaries {
		text := strings.TrimSpace(summary.PrimaryText)
		if text == "" {
			continue
		}
		if _, exists := seen[text]; exists {
			continue
		}
		kind := strings.TrimSpace(summary.SourceRef)
		dimension := strings.TrimSpace(summary.Dimension)
		intersectionID := strings.TrimSpace(summary.IntersectionID)
		if kind == "" || dimension == "" || intersectionID == "" {
			continue
		}
		class := strings.TrimSpace(summary.IntersectionClass)
		if class == "" {
			class = "fact"
		}
		seen[text] = struct{}{}
		facts = append(facts, map[string]any{
			"intersectionId":    intersectionID,
			"kind":              kind,
			"dimension":         dimension,
			"intersectionClass": class,
			"primaryText":       text,
		})
		if len(facts) == 2 {
			break
		}
	}
	return facts
}
