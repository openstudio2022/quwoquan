package authorimpact

import (
	"strings"
	"time"

	rtimpact "quwoquan_service/runtime/impact"
	"quwoquan_service/services/content-service/internal/application/intersection"
	"quwoquan_service/services/content-service/internal/application/ports"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

// AuthorImpactEvidencePageView is the ListAuthorImpactEvidence response (mirrors
// projections/author_impact_evidence_page.yaml; app reads it directly).
type AuthorImpactEvidencePageView struct {
	ImpactID           string                         `json:"impactId"`
	EvidenceSnapshotID string                         `json:"evidenceSnapshotId"`
	TotalCount         int64                          `json:"totalCount"`
	Items              []AuthorImpactEvidenceItemView `json:"items"`
	NextCursor         string                         `json:"nextCursor"`
	HasMore            bool                           `json:"hasMore"`
}

// AuthorImpactEvidenceItemView is one paginated impact evidence detail row
// (mirrors projections/author_impact_evidence_item.yaml).
type AuthorImpactEvidenceItemView struct {
	EvidenceID            string                                            `json:"evidenceId"`
	ImpactID              string                                            `json:"impactId"`
	HelpType              string                                            `json:"helpType"`
	Action                string                                            `json:"action"`
	IntersectionDimension string                                            `json:"intersectionDimension"`
	OccurredAt            string                                            `json:"occurredAt"`
	SummaryText           string                                            `json:"summaryText"`
	SampleVisual          *intersection.IntersectionVisualView              `json:"sampleVisual,omitempty"`
	RepresentativeActor   *intersection.IntersectionRepresentativeActorView `json:"representativeActor,omitempty"`
	ActionHints           []intersection.IntersectionActionHintView         `json:"actionHints"`
	ContentTarget         *intersection.IntersectionTargetView              `json:"contentTarget,omitempty"`
}

// BuildAuthorImpactEvidencePage hydrates raw evidence facts into the client view:
// content title/cover (read-path hydration), cloud-side conclusion sentence (G2),
// and a content-anchored drill-down target. resolveImageURL may be nil.
func BuildAuthorImpactEvidencePage(
	raws []ports.AuthorImpactEvidenceRaw,
	posts map[string]*postmodel.Post,
	resolveImageURL func(string) string,
	impactID string,
	evidenceSnapshotID string,
	nextCursor string,
	total int64,
	hasMore bool,
	viewerIsAuthor bool,
) AuthorImpactEvidencePageView {
	perspective := rtimpact.ActorTA
	if viewerIsAuthor {
		perspective = rtimpact.ActorSelf
	}
	items := make([]AuthorImpactEvidenceItemView, 0, len(raws))
	for _, raw := range raws {
		var post *postmodel.Post
		if posts != nil {
			post = posts[strings.TrimSpace(raw.ContentID)]
		}
		title := ""
		if post != nil {
			title = strings.TrimSpace(post.Title)
		}
		item := AuthorImpactEvidenceItemView{
			EvidenceID:            raw.EvidenceID,
			ImpactID:              raw.ImpactID,
			HelpType:              raw.HelpType,
			Action:                raw.Action,
			IntersectionDimension: raw.IntersectionDimension,
			OccurredAt:            raw.OccurredAt.UTC().Format(time.RFC3339),
			SummaryText:           rtimpact.EvidenceText(raw.HelpType, raw.Action, title, perspective),
			RepresentativeActor: &intersection.IntersectionRepresentativeActorView{
				DisplayName:   "有人",
				RelationLabel: "被影响的人",
				PrivacyState:  "anonymous",
			},
		}
		if visual := evidenceContentVisual(raw, post, resolveImageURL); visual != nil {
			item.SampleVisual = visual
			item.ContentTarget = visual.Target
		}
		item.ActionHints = impactEvidenceActionHints(raw.HelpType, item.ContentTarget)
		items = append(items, item)
	}
	if evidenceSnapshotID == "" {
		evidenceSnapshotID = impactID
	}
	return AuthorImpactEvidencePageView{
		ImpactID:           impactID,
		EvidenceSnapshotID: evidenceSnapshotID,
		TotalCount:         total,
		Items:              items,
		NextCursor:         nextCursor,
		HasMore:            hasMore,
	}
}

// impactEvidenceActionHints 查 helpType → 证据明细行主行动
// （rtimpact.EvidenceActionByHelpType，源 registry.helpTypes[].evidenceAction）。
// 未登记 helpType 兜底 DefaultEvidenceAction（查看内容）。
func impactEvidenceActionHints(helpType string, target *intersection.IntersectionTargetView) []intersection.IntersectionActionHintView {
	action, ok := rtimpact.EvidenceActionByHelpType[strings.TrimSpace(helpType)]
	if !ok {
		action = rtimpact.DefaultEvidenceAction
	}
	return []intersection.IntersectionActionHintView{{
		ActionKey: action.Key,
		Label:     action.Label,
		Target:    target,
		IsPrimary: true,
		Priority:  1,
	}}
}

// evidenceContentVisual builds the content-anchored sample visual. Returns nil
// when there is no resolvable content (no fabricated placeholder).
func evidenceContentVisual(raw ports.AuthorImpactEvidenceRaw, post *postmodel.Post, resolveImageURL func(string) string) *intersection.IntersectionVisualView {
	contentID := strings.TrimSpace(raw.ContentID)
	if contentID == "" {
		return nil
	}
	imageURL := ""
	displayName := ""
	if post != nil {
		imageURL = strings.TrimSpace(post.CoverUrl)
		if imageURL == "" && len(post.MediaUrls) > 0 {
			imageURL = strings.TrimSpace(post.MediaUrls[0])
		}
		displayName = strings.TrimSpace(post.Title)
	}
	if resolveImageURL != nil && imageURL != "" {
		imageURL = resolveImageURL(imageURL)
	}
	return &intersection.IntersectionVisualView{
		AssetKind:   "content",
		ImageURL:    imageURL,
		DisplayName: displayName,
		Target: &intersection.IntersectionTargetView{
			ObjectID:   contentID,
			ObjectKind: "content",
			RouteID:    "contentDetail",
		},
	}
}
