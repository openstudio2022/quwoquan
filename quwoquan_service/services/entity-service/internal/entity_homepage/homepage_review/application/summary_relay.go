package homepage_review

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	reviewports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

const reviewSummaryConsumer = "entity.homepage-review-summary"

type HomepageSummaryProjector interface {
	ApplyReviewSummary(
		ctx context.Context,
		homepageID string,
		averageRating *float64,
		ratingCount int,
		highlightTags []string,
	) error
}

type SummaryRelay struct {
	outbox      reviewports.OutboxReader
	checkpoints reviewports.ProjectionCheckpointStore
	summaries   reviewports.SummaryReader
	homepages   HomepageSummaryProjector
}

func NewSummaryRelay(
	outbox reviewports.OutboxReader,
	checkpoints reviewports.ProjectionCheckpointStore,
	summaries reviewports.SummaryReader,
	homepages HomepageSummaryProjector,
) (*SummaryRelay, error) {
	if outbox == nil || checkpoints == nil || summaries == nil || homepages == nil {
		return nil, fmt.Errorf("homepage review summary relay requires outbox, checkpoint, summary and homepage ports")
	}
	return &SummaryRelay{
		outbox: outbox, checkpoints: checkpoints, summaries: summaries, homepages: homepages,
	}, nil
}

func (r *SummaryRelay) RunOnce(ctx context.Context, limit int) (int, error) {
	checkpoint, err := r.checkpoints.LoadCheckpoint(ctx, reviewSummaryConsumer)
	if err != nil {
		return 0, err
	}
	events, err := r.outbox.ReadAfter(ctx, checkpoint, limit)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, event := range events {
		homepageID, err := reviewHomepageID(event)
		if err != nil {
			return processed, err
		}
		summary, err := r.summaries.SummarizeByHomepage(ctx, homepageID)
		if err != nil {
			return processed, err
		}
		if err := r.homepages.ApplyReviewSummary(
			ctx,
			homepageID,
			summary.AverageRating,
			summary.RatingCount,
			summary.HighlightTags,
		); err != nil {
			return processed, err
		}
		if err := r.checkpoints.SaveCheckpoint(
			ctx,
			reviewSummaryConsumer,
			event.EventID,
		); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func reviewHomepageID(event reviewports.OutboxEvent) (string, error) {
	switch event.EventType {
	case EventReviewPublished, EventReviewUpdated, EventReviewRemoved:
	default:
		return "", fmt.Errorf("unsupported homepage review outbox event %q", event.EventType)
	}
	var payload struct {
		HomepageID string `json:"homepageId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return "", fmt.Errorf("decode %s payload: %w", event.EventType, err)
	}
	if strings.TrimSpace(payload.HomepageID) == "" {
		return "", fmt.Errorf("%s payload has empty homepageId", event.EventType)
	}
	return strings.TrimSpace(payload.HomepageID), nil
}
