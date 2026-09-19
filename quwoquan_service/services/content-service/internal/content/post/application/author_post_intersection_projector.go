package post

import (
	"context"
	"strings"

	"quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// AuthorPostIntersectionPoolReader returns one viewer's canonical reason pool.
// The application query reads it once per page and matches reasons to posts in
// memory; persistence adapters never query Recommendation and no per-post read
// is permitted.
type AuthorPostIntersectionPoolReader interface {
	Feed(ctx context.Context, viewerID, channel string, limit int) ([]intersection.IntersectionReasonView, error)
}

type AuthorPostClientItem struct {
	postports.AuthorPostItemSlice
	IntersectionReasons []intersection.IntersectionReasonView `json:"intersectionReasons,omitempty"`
}

type AuthorPostClientPage struct {
	Items      []AuthorPostClientItem `json:"items"`
	NextCursor string                 `json:"nextCursor,omitempty"`
	HasMore    bool                   `json:"hasMore"`
}

// ProjectAuthorPostIntersections attaches at most one display-ready canonical
// reason to each Post while preserving the author's list identity and order.
func ProjectAuthorPostIntersections(
	ctx context.Context,
	page postports.AuthorPostPageSlice,
	viewerID string,
	reader AuthorPostIntersectionPoolReader,
) (AuthorPostClientPage, error) {
	result := AuthorPostClientPage{
		Items:      make([]AuthorPostClientItem, 0, len(page.Items)),
		NextCursor: page.NextCursor,
		HasMore:    page.HasMore,
	}
	for _, item := range page.Items {
		result.Items = append(result.Items, AuthorPostClientItem{AuthorPostItemSlice: item})
	}
	viewerID = strings.TrimSpace(viewerID)
	if viewerID == "" || reader == nil || len(result.Items) == 0 {
		return result, nil
	}
	reasons, err := reader.Feed(ctx, viewerID, "", feedapp.IntersectionReasonPoolLimit)
	if err != nil {
		return result, err
	}
	for index := range result.Items {
		item := result.Items[index].AuthorPostItemSlice
		result.Items[index].IntersectionReasons = feedapp.IntersectionsForPost(
			feedapp.FeedItemView{
				PostID:              string(item.PostID),
				PrimaryHomepageID:   item.PrimaryHomepageID,
				PrimaryHomepageType: item.PrimaryHomepageType,
				GatheringRef:        item.GatheringRef,
			},
			reasons,
		)
	}
	return result, nil
}
