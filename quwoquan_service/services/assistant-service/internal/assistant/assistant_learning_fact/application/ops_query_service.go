package application

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

type OpsProjectionReader interface {
	GetLearningProjection(
		context.Context,
		string,
	) (*model.LearningProjection, error)
}

// OpsQueryService owns the GetLearningOpsSummary application query. Keeping
// the reader and projection view under AssistantLearningFact prevents the
// conversation aggregate from becoming a second owner of learning state.
type OpsQueryService struct {
	projections OpsProjectionReader
}

func NewOpsQueryService(projections OpsProjectionReader) *OpsQueryService {
	return &OpsQueryService{projections: projections}
}

func (service *OpsQueryService) GetLearningOpsSummary(
	ctx context.Context,
	userID string,
) (_ model.AssistantLearningOpsSummaryView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.learning_fact.GetLearningOpsSummary",
		attribute.String("user.id", userID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	userID = strings.TrimSpace(userID)
	if userID == "" {
		recordLearningOpsQuery("unauthorized")
		return model.AssistantLearningOpsSummaryView{}, ErrUnauthorized
	}
	if service == nil || service.projections == nil {
		recordLearningOpsQuery("store_failed")
		return model.AssistantLearningOpsSummaryView{}, ErrStoreUnavailable
	}
	profile, readErr := service.projections.GetLearningProjection(ctx, userID)
	if readErr != nil {
		recordLearningOpsQuery("store_failed")
		return model.AssistantLearningOpsSummaryView{}, fmt.Errorf(
			"%w: read learning ops projection: %v",
			ErrStoreUnavailable,
			readErr,
		)
	}
	if profile == nil {
		profile = &model.LearningProjection{UserID: userID}
	}
	metricAverages := make(map[string]float64, len(profile.MetricSampleCounts))
	for metricID, sampleCount := range profile.MetricSampleCounts {
		if sampleCount > 0 {
			metricAverages[metricID] = profile.MetricScoreSums[metricID] /
				float64(sampleCount)
		}
	}
	if len(metricAverages) == 0 {
		metricAverages = nil
	}
	summary := model.AssistantLearningOpsSummaryView{
		UserID:                profile.UserID,
		TotalFeedbackCount:    profile.TotalFeedbackCount,
		PositiveFeedbackCount: profile.PositiveFeedbackCount,
		NegativeFeedbackCount: profile.NegativeFeedbackCount,
		TextFeedbackCount:     profile.TextFeedbackCount,
		HighPriorityCount:     profile.HighPriorityCount,
		MediumPriorityCount:   profile.MediumPriorityCount,
		LastFeedbackType:      profile.LastFeedbackType,
		LastFeedbackScore:     profile.LastFeedbackScore,
		LastMetricID:          profile.LastMetricID,
		LastMetricScore:       profile.LastMetricScore,
		TopReasonCodes:        topReasonCodes(profile.ReasonCodeCounts, 5),
		MetricAverages:        metricAverages,
		LatestMetricScores:    cloneMetricScores(profile.LatestMetricScores),
	}
	if !profile.LastFeedbackAt.IsZero() {
		summary.LastFeedbackAt = profile.LastFeedbackAt.UTC().Format(time.RFC3339)
	}
	if !profile.UpdatedAt.IsZero() {
		summary.UpdatedAt = profile.UpdatedAt.UTC().Format(time.RFC3339)
	}
	recordLearningOpsQuery("success")
	return summary, nil
}

func topReasonCodes(counts map[string]int64, limit int) []string {
	if len(counts) == 0 || limit <= 0 {
		return nil
	}
	type reasonCount struct {
		reason string
		count  int64
	}
	items := make([]reasonCount, 0, len(counts))
	for reason, count := range counts {
		items = append(items, reasonCount{reason: reason, count: count})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].count != items[j].count {
			return items[i].count > items[j].count
		}
		return items[i].reason < items[j].reason
	})
	if len(items) > limit {
		items = items[:limit]
	}
	out := make([]string, 0, len(items))
	for _, item := range items {
		out = append(out, item.reason)
	}
	return out
}

func cloneMetricScores(source map[string]float64) map[string]float64 {
	if len(source) == 0 {
		return nil
	}
	out := make(map[string]float64, len(source))
	for key, value := range source {
		out[key] = value
	}
	return out
}
