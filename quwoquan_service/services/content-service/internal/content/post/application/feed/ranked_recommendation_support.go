package feed

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
)

func WithRankedRecommendationGateway(
	gateway deliveryapp.RankedRecommendationGateway,
) FeedServiceOption {
	return func(service *FeedService) {
		service.rankedWindows = gateway
	}
}

func WithFeedPageDeliveredPublisher(
	publisher deliveryapp.FeedPageDeliveredPublisher,
) FeedServiceOption {
	return func(service *FeedService) {
		service.deliveryEvents = publisher
	}
}

type rankedRecommendationDelivery struct {
	page      transport.RankedRecommendationPage
	delivered []deliveryapp.DeliveredRecommendationItem
}

func (delivery *rankedRecommendationDelivery) bindPage(
	page transport.RankedRecommendationPage,
) error {
	if delivery == nil {
		return deliveryapp.ErrRecommendationUnavailable
	}
	if delivery.page.WindowId == "" {
		delivery.page = page
		return nil
	}
	if delivery.page.WindowId != page.WindowId ||
		delivery.page.Scenario != page.Scenario ||
		delivery.page.ModelBucket != page.ModelBucket ||
		delivery.page.PolicyDigest != page.PolicyDigest ||
		delivery.page.RankingSnapshotDigest != page.RankingSnapshotDigest ||
		!delivery.page.FeatureSnapshotAt.Equal(page.FeatureSnapshotAt) ||
		!delivery.page.ExpiresAt.Equal(page.ExpiresAt) {
		return fmt.Errorf(
			"%w: recommendation page attribution changed within one response",
			deliveryapp.ErrRecommendationUnavailable,
		)
	}
	return nil
}

func (delivery *rankedRecommendationDelivery) event(
	deliveryPageID string,
	feedRequestID string,
	subjectID string,
	personaID string,
	occurredAt time.Time,
) deliveryapp.FeedPageDelivered {
	return deliveryapp.FeedPageDelivered{
		DeliveryPageID:        deliveryPageID,
		FeedRequestID:         feedRequestID,
		SubjectID:             subjectID,
		PersonaID:             personaID,
		Scenario:              delivery.page.Scenario,
		WindowID:              delivery.page.WindowId,
		ModelBucket:           delivery.page.ModelBucket,
		ModelChannel:          delivery.page.ModelChannel,
		ModelReleaseID:        delivery.page.ModelReleaseId,
		RankingSnapshotDigest: delivery.page.RankingSnapshotDigest,
		FeatureSnapshotAt:     delivery.page.FeatureSnapshotAt,
		UserFeatureSnapshot:   cloneSnapshot(delivery.page.UserFeatureSnapshot),
		Items:                 append([]deliveryapp.DeliveredRecommendationItem(nil), delivery.delivered...),
		OccurredAt:            occurredAt,
	}
}

func recommendationScenario(route feedRoute) string {
	switch {
	case route.Surface == "premium_stream":
		return "premium_stream"
	case route.Vertical == "travel_photography":
		return "travel_photography"
	default:
		return "content_feed"
	}
}

func rankedRecommendationSubject(req ListFeedRequest) string {
	if !identity.IsAnonymousFallbackPersonaID(req.UserID) {
		return strings.TrimSpace(req.UserID)
	}
	return identity.RankedFeedWindowSubjectID(req.UserID, req.SessionID)
}

func (s *FeedService) rankedRecommendationPage(
	ctx context.Context,
	req ListFeedRequest,
	route feedRoute,
	feedRequestID string,
	continuation *rtrec.RankedFeedContinuation,
	limit int,
) (transport.RankedRecommendationPage, error) {
	if s == nil || s.rankedWindows == nil {
		return transport.RankedRecommendationPage{}, deliveryapp.ErrRecommendationUnavailable
	}
	scenario := recommendationScenario(route)
	var (
		page transport.RankedRecommendationPage
		err  error
	)
	if continuation == nil {
		page, err = s.rankedWindows.Create(
			ctx,
			transport.CreateRankedRecommendationWindowCommand{
				IdempotencyKey: strings.TrimSpace(feedRequestID),
				SubjectId:      rankedRecommendationSubject(req),
				Scenario:       scenario,
				Limit:          limit,
			},
		)
	} else {
		page, err = s.rankedWindows.GetPage(
			ctx,
			strings.TrimSpace(continuation.WindowID),
			continuation.AfterOrdinal,
			limit,
		)
	}
	if err != nil {
		return transport.RankedRecommendationPage{}, err
	}
	if page.Scenario != scenario ||
		(continuation != nil && page.WindowId != strings.TrimSpace(continuation.WindowID)) {
		return transport.RankedRecommendationPage{}, fmt.Errorf(
			"%w: recommendation continuation binding changed",
			deliveryapp.ErrRecommendationUnavailable,
		)
	}
	return page, nil
}

func rankedFeedItem(item transport.RankedRecommendationItem) rtrec.FeedItem {
	return rtrec.FeedItem{
		ContentID:       strings.TrimSpace(item.ContentId),
		Score:           item.Score,
		QualityScore:    item.Score,
		RecallPath:      snapshotText(item.ItemFeatureSnapshot, "recallPath"),
		ContentVertical: snapshotText(item.ItemFeatureSnapshot, "contentVertical"),
		SupplySource:    snapshotText(item.ItemFeatureSnapshot, "supplySource"),
	}
}

func snapshotText(snapshot map[string]any, key string) string {
	value, ok := snapshot[key]
	if !ok || value == nil {
		return ""
	}
	text, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(text)
}

func rankedContinuation(
	page transport.RankedRecommendationPage,
) *rtrec.RankedFeedContinuation {
	if page.NextOrdinal == nil {
		return nil
	}
	afterContentID := ""
	if len(page.Items) > 0 {
		afterContentID = strings.TrimSpace(page.Items[len(page.Items)-1].ContentId)
	}
	return &rtrec.RankedFeedContinuation{
		WindowID:       strings.TrimSpace(page.WindowId),
		AfterOrdinal:   *page.NextOrdinal,
		AfterContentID: afterContentID,
		ExpiresAt:      page.ExpiresAt.UTC(),
	}
}

func deliveredRecommendationItem(
	item transport.RankedRecommendationItem,
	view FeedItemView,
) deliveryapp.DeliveredRecommendationItem {
	return deliveryapp.DeliveredRecommendationItem{
		Ordinal:               item.Ordinal,
		ContentID:             strings.TrimSpace(item.ContentId),
		ContentType:           strings.TrimSpace(view.ContentType),
		FeatureSnapshotDigest: strings.TrimSpace(item.FeatureSnapshotDigest),
		ItemFeatureSnapshot:   cloneSnapshot(item.ItemFeatureSnapshot),
	}
}

func cloneSnapshot(source map[string]any) map[string]any {
	clone := make(map[string]any, len(source))
	for key, value := range source {
		clone[key] = value
	}
	return clone
}
