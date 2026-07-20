package homepage_review

import (
	"context"
	"testing"
	"time"

	reviewports "quwoquan_service/services/entity-service/internal/domain/homepage_review/ports"
)

func TestSummaryRelayProjectsDurableReviewFactExactlyOnce(t *testing.T) {
	source := &summaryRelaySource{
		events: []reviewports.OutboxEvent{{
			EventID: "review-event-1", EventType: EventReviewPublished,
			AggregateID: "review-1", AggregateVersion: 1,
			Payload:    []byte(`{"reviewId":"review-1","homepageId":"homepage-1"}`),
			OccurredAt: time.Date(2026, 7, 20, 1, 0, 0, 0, time.UTC),
		}},
		summary: reviewports.Summary{
			AverageRating: floatPointer(4.5),
			RatingCount:   2,
			HighlightTags: []string{"景色开阔"},
		},
	}
	projector := &summaryProjectorCapture{}
	relay, err := NewSummaryRelay(source, source, source, projector)
	if err != nil {
		t.Fatalf("new relay: %v", err)
	}
	processed, err := relay.RunOnce(context.Background(), 10)
	if err != nil || processed != 1 {
		t.Fatalf("run relay: processed=%d err=%v", processed, err)
	}
	if projector.homepageID != "homepage-1" ||
		projector.count != 2 ||
		len(projector.tags) != 1 {
		t.Fatalf("summary projection mismatch: %+v", projector)
	}
	if replayed, err := relay.RunOnce(context.Background(), 10); err != nil || replayed != 0 {
		t.Fatalf("relay replay mismatch: processed=%d err=%v", replayed, err)
	}
}

type summaryRelaySource struct {
	events     []reviewports.OutboxEvent
	checkpoint string
	summary    reviewports.Summary
}

func (s *summaryRelaySource) ReadAfter(
	_ context.Context,
	checkpoint string,
	_ int,
) ([]reviewports.OutboxEvent, error) {
	if checkpoint == "" {
		return append([]reviewports.OutboxEvent(nil), s.events...), nil
	}
	return []reviewports.OutboxEvent{}, nil
}

func (s *summaryRelaySource) LoadCheckpoint(
	context.Context,
	string,
) (string, error) {
	return s.checkpoint, nil
}

func (s *summaryRelaySource) SaveCheckpoint(
	_ context.Context,
	_ string,
	checkpoint string,
) error {
	s.checkpoint = checkpoint
	return nil
}

func (s *summaryRelaySource) SummarizeByHomepage(
	context.Context,
	string,
) (reviewports.Summary, error) {
	return s.summary, nil
}

type summaryProjectorCapture struct {
	homepageID string
	average    *float64
	count      int
	tags       []string
}

func (p *summaryProjectorCapture) ApplyReviewSummary(
	_ context.Context,
	homepageID string,
	averageRating *float64,
	ratingCount int,
	highlightTags []string,
) error {
	p.homepageID = homepageID
	p.average = averageRating
	p.count = ratingCount
	p.tags = append([]string(nil), highlightTags...)
	return nil
}

func floatPointer(value float64) *float64 {
	return &value
}
