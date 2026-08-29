package application

import (
	"context"
	"errors"
	"strings"
	"time"

	transport "quwoquan_service/services/content-service/generated/content/feed_delivery_page"
)

var (
	ErrRecommendationUnavailable = errors.New("ranked recommendation window is unavailable")
	ErrDeliveryEventInvalid      = errors.New("feed page delivered event is invalid")
)

// RankedRecommendationGateway is the only outbound recommendation boundary
// used by Content. Its types are generated from Recommendation's canonical
// RankedRecommendationWindow contract.
type RankedRecommendationGateway interface {
	Create(
		context.Context,
		transport.CreateRankedRecommendationWindowCommand,
	) (transport.RankedRecommendationPage, error)
	GetPage(
		context.Context,
		transport.GetRankedRecommendationPageQuery,
	) (transport.RankedRecommendationPage, error)
}

type DeliveredRecommendationItem struct {
	Ordinal               int            `json:"ordinal"`
	ContentID             string         `json:"contentId"`
	ContentType           string         `json:"contentType"`
	FeatureSnapshotDigest string         `json:"featureSnapshotDigest"`
	ItemFeatureSnapshot   map[string]any `json:"itemFeatureSnapshot"`
}

// FeedPageDelivered is the domain event emitted only after the immutable
// FeedDeliveryPage has been persisted and the listed Post identities survived
// current Content visibility hydration.
type FeedPageDelivered struct {
	DeliveryPageID        string                        `json:"deliveryPageId"`
	FeedRequestID         string                        `json:"feedRequestId"`
	SubjectID             string                        `json:"subjectId"`
	PersonaID             string                        `json:"personaId,omitempty"`
	Scenario              string                        `json:"scenario"`
	WindowID              string                        `json:"windowId"`
	ExperimentBucket      string                        `json:"experimentBucket"`
	ModelBucket           string                        `json:"modelBucket"`
	ModelChannel          *string                       `json:"modelChannel,omitempty"`
	ModelReleaseID        *string                       `json:"modelReleaseId,omitempty"`
	RankingSnapshotDigest string                        `json:"rankingSnapshotDigest"`
	FeatureSnapshotAt     time.Time                     `json:"featureSnapshotAt"`
	UserFeatureSnapshot   map[string]any                `json:"userFeatureSnapshot"`
	Items                 []DeliveredRecommendationItem `json:"items"`
	OccurredAt            time.Time                     `json:"occurredAt"`
}

func (event FeedPageDelivered) Validate() error {
	if !allNonBlank(
		event.DeliveryPageID,
		event.FeedRequestID,
		event.SubjectID,
		event.Scenario,
		event.WindowID,
		event.ExperimentBucket,
		event.ModelBucket,
		event.RankingSnapshotDigest,
	) || event.FeatureSnapshotAt.IsZero() || event.OccurredAt.IsZero() ||
		event.FeatureSnapshotAt.After(event.OccurredAt) ||
		event.UserFeatureSnapshot == nil || len(event.Items) == 0 || len(event.Items) > 20 {
		return ErrDeliveryEventInvalid
	}
	if event.ExperimentBucket != "model" && event.ExperimentBucket != "rule" {
		return ErrDeliveryEventInvalid
	}
	modelChannel := optionalText(event.ModelChannel)
	modelReleaseID := optionalText(event.ModelReleaseID)
	switch event.ModelBucket {
	case "model":
		if modelChannel == "" || modelReleaseID == "" {
			return ErrDeliveryEventInvalid
		}
	case "rule":
		if modelChannel != "" || modelReleaseID != "" {
			return ErrDeliveryEventInvalid
		}
	default:
		return ErrDeliveryEventInvalid
	}
	ordinals := make(map[int]struct{}, len(event.Items))
	contentIDs := make(map[string]struct{}, len(event.Items))
	for _, item := range event.Items {
		contentID := strings.TrimSpace(item.ContentID)
		if item.Ordinal < 0 || contentID == "" || strings.TrimSpace(item.ContentType) == "" ||
			strings.TrimSpace(item.FeatureSnapshotDigest) == "" || item.ItemFeatureSnapshot == nil {
			return ErrDeliveryEventInvalid
		}
		if _, duplicate := ordinals[item.Ordinal]; duplicate {
			return ErrDeliveryEventInvalid
		}
		if _, duplicate := contentIDs[contentID]; duplicate {
			return ErrDeliveryEventInvalid
		}
		ordinals[item.Ordinal] = struct{}{}
		contentIDs[contentID] = struct{}{}
	}
	return nil
}

type FeedPageDeliveredPublisher interface {
	Publish(context.Context, FeedPageDelivered) error
}

func allNonBlank(values ...string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == "" {
			return false
		}
	}
	return true
}

func optionalText(value *string) string {
	if value == nil {
		return ""
	}
	return strings.TrimSpace(*value)
}
