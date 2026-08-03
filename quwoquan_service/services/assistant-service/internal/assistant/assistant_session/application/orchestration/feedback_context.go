package orchestration

import (
	"context"
	"sort"
	"strings"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
)

const (
	assistantLearningConsentSkillID = "assistant_learning"
	assistantLearningContextScope   = "assistant_learning_context"
)

// ResolveFeedbackContextSnapshot returns the consent- and policy-filtered
// snapshot frozen into a run. It fails closed without trusted owner evidence.
func (service *AssistantService) ResolveFeedbackContextSnapshot(
	ctx context.Context,
	userID string,
	personaID string,
	policy assistant.AssistantFrozenLearningContextPolicy,
	now time.Time,
) assistant.AssistantFeedbackContextSnapshot {
	noInjection := func(decision string) assistant.AssistantFeedbackContextSnapshot {
		recordFeedbackContextDecision(decision)
		return assistant.AssistantFeedbackContextSnapshot{
			Decision:                 decision,
			WindowDays:               policy.WindowDays,
			SnapshotTrainingEligible: false,
		}
	}
	if !policy.Enabled {
		return noInjection("policy_disabled")
	}
	if service.consents == nil {
		return noInjection("consent_unavailable")
	}
	consents, err := service.consents.ListActiveConsents(ctx, userID)
	if err != nil {
		return noInjection("consent_unavailable")
	}
	var matchedConsent consentmodel.Consent
	for _, consent := range consents {
		if strings.TrimSpace(consent.SkillID) == assistantLearningConsentSkillID &&
			containsScope(consent.GrantedScopes, assistantLearningContextScope) {
			matchedConsent = consent
			break
		}
	}
	if strings.TrimSpace(matchedConsent.ID) == "" ||
		matchedConsent.GrantedAt.IsZero() {
		return noInjection("consent_missing_or_opted_out")
	}
	if service.learningProjection == nil {
		return noInjection("projection_unavailable")
	}
	projection, err := service.learningProjection.GetLearningProjectionForPersona(
		ctx,
		userID,
		personaID,
	)
	if err != nil {
		return noInjection("projection_unavailable")
	}
	if projection == nil {
		return noInjection("insufficient_samples")
	}
	if strings.TrimSpace(projection.UserID) != strings.TrimSpace(userID) ||
		strings.TrimSpace(projection.PersonaID) != strings.TrimSpace(personaID) {
		return noInjection("owner_mismatch")
	}
	window := aggregateFeedbackWindow(projection, policy.WindowDays, now)
	if window.feedbackSamples < int64(policy.MinimumFeedbackSamples) {
		return noInjection("insufficient_samples")
	}
	signals := stringSet(policy.AllowedSignals)
	snapshot := assistant.AssistantFeedbackContextSnapshot{
		Decision:                 "injected",
		ConsentID:                matchedConsent.ID,
		ConsentGrantedAt:         matchedConsent.GrantedAt.UTC(),
		DefinitionDigest:         projection.DefinitionDigest,
		SourceWatermarkSequence:  projection.WatermarkSequence,
		WindowDays:               policy.WindowDays,
		FeedbackSampleCount:      window.feedbackSamples,
		SnapshotTrainingEligible: policy.SnapshotTrainingEligible,
	}
	if _, ok := signals["feedback_counts"]; ok {
		snapshot.PositiveFeedbackCount = window.positive
		snapshot.NegativeFeedbackCount = window.negative
		snapshot.TextFeedbackCount = window.text
	}
	if _, ok := signals["metric_summaries"]; ok {
		snapshot.Metrics = feedbackMetricSummaries(
			window,
			stringSet(policy.AllowedMetricIDs),
		)
	}
	if _, ok := signals["top_reason_codes"]; ok {
		snapshot.Reasons = feedbackReasonSummaries(
			window.reasonCounts,
			stringSet(policy.AllowedReasonCodes),
		)
	}
	recordFeedbackContextDecision(snapshot.Decision)
	return snapshot
}

func containsScope(values []string, expected string) bool {
	expected = strings.TrimSpace(expected)
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

type feedbackWindowAggregate struct {
	feedbackSamples int64
	positive        int64
	negative        int64
	text            int64
	metricSamples   map[string]int64
	metricSums      map[string]float64
	metricLatest    map[string]float64
	reasonCounts    map[string]int64
}

func aggregateFeedbackWindow(
	projection *learningmodel.LearningProjection,
	windowDays int,
	now time.Time,
) feedbackWindowAggregate {
	result := feedbackWindowAggregate{
		metricSamples: map[string]int64{},
		metricSums:    map[string]float64{},
		metricLatest:  map[string]float64{},
		reasonCounts:  map[string]int64{},
	}
	cutoff := now.UTC().AddDate(0, 0, -(windowDays - 1))
	cutoffKey := cutoff.Format("2006-01-02")
	keys := make([]string, 0, len(projection.DailyBuckets))
	for key := range projection.DailyBuckets {
		if key >= cutoffKey {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	for _, key := range keys {
		bucket := projection.DailyBuckets[key]
		result.feedbackSamples += bucket.FeedbackCount
		result.positive += bucket.PositiveFeedbackCount
		result.negative += bucket.NegativeFeedbackCount
		result.text += bucket.TextFeedbackCount
		for metricID, count := range bucket.MetricSampleCounts {
			result.metricSamples[metricID] += count
			result.metricSums[metricID] += bucket.MetricScoreSums[metricID]
		}
		for metricID, latest := range bucket.LatestMetricScores {
			result.metricLatest[metricID] = latest
		}
		for reason, count := range bucket.ReasonCodeCounts {
			result.reasonCounts[reason] += count
		}
	}
	return result
}

func feedbackMetricSummaries(
	window feedbackWindowAggregate,
	allowlist map[string]struct{},
) []assistant.AssistantFeedbackMetricSummary {
	metricIDs := make([]string, 0, len(window.metricSamples))
	for metricID, count := range window.metricSamples {
		if count <= 0 {
			continue
		}
		if _, allowed := allowlist[metricID]; !allowed {
			continue
		}
		metricIDs = append(metricIDs, metricID)
	}
	sort.Strings(metricIDs)
	result := make([]assistant.AssistantFeedbackMetricSummary, 0, len(metricIDs))
	for _, metricID := range metricIDs {
		count := window.metricSamples[metricID]
		result = append(result, assistant.AssistantFeedbackMetricSummary{
			MetricID:    metricID,
			SampleCount: count,
			Average:     window.metricSums[metricID] / float64(count),
			Latest:      window.metricLatest[metricID],
		})
	}
	return result
}

func feedbackReasonSummaries(
	counts map[string]int64,
	allowlist map[string]struct{},
) []assistant.AssistantFeedbackReasonSummary {
	type pair struct {
		code  string
		count int64
	}
	items := make([]pair, 0, len(counts))
	for code, count := range counts {
		if count <= 0 {
			continue
		}
		if _, allowed := allowlist[code]; !allowed {
			continue
		}
		items = append(items, pair{code: code, count: count})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].count != items[j].count {
			return items[i].count > items[j].count
		}
		return items[i].code < items[j].code
	})
	if len(items) > 5 {
		items = items[:5]
	}
	result := make([]assistant.AssistantFeedbackReasonSummary, 0, len(items))
	for _, item := range items {
		result = append(result, assistant.AssistantFeedbackReasonSummary{
			ReasonCode: item.code,
			Count:      item.count,
		})
	}
	return result
}

func stringSet(values []string) map[string]struct{} {
	result := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			result[value] = struct{}{}
		}
	}
	return result
}
