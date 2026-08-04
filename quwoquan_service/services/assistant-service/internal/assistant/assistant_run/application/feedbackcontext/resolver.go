package feedbackcontext

import (
	"context"
	"sort"
	"strings"
	"time"

	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

const ResolverRef = "run.feedback_context"

type ConsentReader interface {
	ListActiveConsents(context.Context, string) ([]consentmodel.Consent, error)
}

type ProjectionReader interface {
	GetLearningProjectionForPersona(
		context.Context,
		string,
		string,
	) (*learningmodel.LearningProjection, error)
}

type Request struct {
	AccountID string
	PersonaID string
	SkillID   string
	// ConsentScope is resolved from the selected Skill's frozen ContextProfile;
	// callers cannot substitute a platform-wide or synthetic Skill grant.
	ConsentScope string
	Policy       assistantmodel.AssistantFrozenLearningContextPolicy
	FrozenAt     time.Time
}

// Resolver owns the privacy boundary between mutable learning projections and
// an immutable AssistantRun. Every non-authorized or untrusted condition
// returns an explicit no-injection snapshot; it never reuses an older value.
type Resolver struct {
	consents    ConsentReader
	projections ProjectionReader
}

func NewResolver(consents ConsentReader, projections ProjectionReader) *Resolver {
	return &Resolver{consents: consents, projections: projections}
}

func (resolver *Resolver) Resolve(
	ctx context.Context,
	request Request,
) assistantmodel.AssistantFeedbackContextSnapshot {
	policy := request.Policy
	noInjection := func(decision string) assistantmodel.AssistantFeedbackContextSnapshot {
		recordDecision(decision)
		return assistantmodel.AssistantFeedbackContextSnapshot{
			Decision:                 decision,
			WindowDays:               policy.WindowDays,
			SnapshotTrainingEligible: false,
		}
	}
	if !policy.Enabled {
		return noInjection("policy_disabled")
	}
	if !validPolicy(policy) {
		return noInjection("policy_invalid")
	}
	accountID := strings.TrimSpace(request.AccountID)
	personaID := strings.TrimSpace(request.PersonaID)
	skillID := strings.TrimSpace(request.SkillID)
	consentScope := strings.TrimSpace(request.ConsentScope)
	if accountID == "" || personaID == "" {
		return noInjection("owner_unresolved")
	}
	if skillID == "" {
		return noInjection("skill_unresolved")
	}
	if consentScope == "" {
		return noInjection("scope_unresolved")
	}
	if resolver == nil || resolver.consents == nil {
		return noInjection("consent_unavailable")
	}
	consents, err := resolver.consents.ListActiveConsents(ctx, accountID)
	if err != nil {
		return noInjection("consent_unavailable")
	}
	var matchedConsent consentmodel.Consent
	for _, consent := range consents {
		if consent.IsGranted() &&
			strings.TrimSpace(consent.AccountID) == accountID &&
			strings.TrimSpace(consent.SkillID) == skillID &&
			containsScope(consent.GrantedScopes, consentScope) {
			matchedConsent = consent
			break
		}
	}
	if strings.TrimSpace(matchedConsent.ID) == "" || matchedConsent.GrantedAt.IsZero() {
		return noInjection("consent_missing_or_opted_out")
	}
	if resolver.projections == nil {
		return noInjection("projection_unavailable")
	}
	projection, err := resolver.projections.GetLearningProjectionForPersona(
		ctx,
		accountID,
		personaID,
	)
	if err != nil {
		return noInjection("projection_unavailable")
	}
	if projection == nil {
		return noInjection("insufficient_samples")
	}
	if strings.TrimSpace(projection.UserID) != accountID ||
		strings.TrimSpace(projection.PersonaID) != personaID {
		return noInjection("owner_mismatch")
	}
	if strings.TrimSpace(projection.DefinitionDigest) !=
		learningmodel.LearningProjectionDefinitionDigest ||
		projection.WatermarkSequence <= 0 {
		return noInjection("projection_untrusted")
	}
	frozenAt := request.FrozenAt.UTC()
	if frozenAt.IsZero() {
		return noInjection("freeze_time_invalid")
	}
	window := aggregateWindow(projection, policy.WindowDays, frozenAt)
	if window.feedbackSamples < int64(policy.MinimumFeedbackSamples) {
		return noInjection("insufficient_samples")
	}
	signals := stringSet(policy.AllowedSignals)
	snapshot := assistantmodel.AssistantFeedbackContextSnapshot{
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
		snapshot.Metrics = metricSummaries(
			window,
			stringSet(policy.AllowedMetricIDs),
		)
	}
	if _, ok := signals["top_reason_codes"]; ok {
		snapshot.Reasons = reasonSummaries(
			window.reasonCounts,
			stringSet(policy.AllowedReasonCodes),
		)
	}
	recordDecision(snapshot.Decision)
	return snapshot
}

// ActiveSkillResolver resolves the feedback authorization scope from the same
// immutable active package snapshot used for Skill routing. This keeps consent
// policy in package assets instead of a Go Skill-ID switch.
type ActiveSkillResolver struct {
	resolver *Resolver
	loader   skillpkg.Loader
}

func NewActiveSkillResolver(
	resolver *Resolver,
	loader skillpkg.Loader,
) *ActiveSkillResolver {
	return &ActiveSkillResolver{resolver: resolver, loader: loader}
}

func (resolver *ActiveSkillResolver) ResolveFeedbackContext(
	ctx context.Context,
	accountID string,
	personaID string,
	skillID string,
	surfaceKind string,
	packageID string,
	releaseDigest string,
	policy assistantmodel.AssistantFrozenLearningContextPolicy,
	frozenAt time.Time,
) assistantmodel.AssistantFeedbackContextSnapshot {
	switch strings.ToLower(strings.TrimSpace(surfaceKind)) {
	case "conversation", "circle":
		return NoInjection("shared_surface_excluded", policy)
	}
	consentScope := ""
	if resolver != nil && resolver.loader != nil {
		frozenContext := skillpkg.WithPackageRelease(ctx, skillpkg.PackageReleaseIdentity{
			PackageID:     strings.TrimSpace(packageID),
			ReleaseDigest: strings.TrimSpace(releaseDigest),
		})
		manifests, err := resolver.loader.Load(frozenContext)
		if err == nil {
			consentScope = feedbackConsentScope(manifests, skillID)
		}
	}
	if resolver == nil || resolver.resolver == nil {
		return NoInjection("projection_unavailable", policy)
	}
	return resolver.resolver.Resolve(ctx, Request{
		AccountID:    accountID,
		PersonaID:    personaID,
		SkillID:      skillID,
		ConsentScope: consentScope,
		Policy:       policy,
		FrozenAt:     frozenAt,
	})
}

func feedbackConsentScope(manifests []skillpkg.Manifest, skillID string) string {
	skillID = strings.TrimSpace(skillID)
	for _, manifest := range manifests {
		if strings.TrimSpace(manifest.SkillID) != skillID {
			continue
		}
		for _, requirement := range manifest.ContextProfile.Requirements {
			if strings.TrimSpace(requirement.ResolverRef) != ResolverRef ||
				len(requirement.ConsentScopes) != 1 {
				continue
			}
			return strings.TrimSpace(requirement.ConsentScopes[0])
		}
		return ""
	}
	return ""
}

func validPolicy(policy assistantmodel.AssistantFrozenLearningContextPolicy) bool {
	if policy.WindowDays < 1 || policy.WindowDays > 90 ||
		policy.MinimumFeedbackSamples < 1 || len(policy.AllowedSignals) == 0 {
		return false
	}
	allowed := map[string]struct{}{
		"feedback_counts":  {},
		"metric_summaries": {},
		"top_reason_codes": {},
	}
	seen := map[string]struct{}{}
	for _, raw := range policy.AllowedSignals {
		value := strings.TrimSpace(raw)
		if _, ok := allowed[value]; !ok || value == "" {
			return false
		}
		if _, duplicate := seen[value]; duplicate {
			return false
		}
		seen[value] = struct{}{}
	}
	return true
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

type windowAggregate struct {
	feedbackSamples int64
	positive        int64
	negative        int64
	text            int64
	metricSamples   map[string]int64
	metricSums      map[string]float64
	metricLatest    map[string]float64
	reasonCounts    map[string]int64
}

func aggregateWindow(
	projection *learningmodel.LearningProjection,
	windowDays int,
	frozenAt time.Time,
) windowAggregate {
	result := windowAggregate{
		metricSamples: map[string]int64{},
		metricSums:    map[string]float64{},
		metricLatest:  map[string]float64{},
		reasonCounts:  map[string]int64{},
	}
	cutoffKey := frozenAt.AddDate(0, 0, -(windowDays - 1)).Format("2006-01-02")
	latestKey := frozenAt.Format("2006-01-02")
	keys := make([]string, 0, len(projection.DailyBuckets))
	for key := range projection.DailyBuckets {
		if key >= cutoffKey && key <= latestKey {
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

func metricSummaries(
	window windowAggregate,
	allowlist map[string]struct{},
) []assistantmodel.AssistantFeedbackMetricSummary {
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
	result := make([]assistantmodel.AssistantFeedbackMetricSummary, 0, len(metricIDs))
	for _, metricID := range metricIDs {
		count := window.metricSamples[metricID]
		result = append(result, assistantmodel.AssistantFeedbackMetricSummary{
			MetricID:    metricID,
			SampleCount: count,
			Average:     window.metricSums[metricID] / float64(count),
			Latest:      window.metricLatest[metricID],
		})
	}
	return result
}

func reasonSummaries(
	counts map[string]int64,
	allowlist map[string]struct{},
) []assistantmodel.AssistantFeedbackReasonSummary {
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
	result := make([]assistantmodel.AssistantFeedbackReasonSummary, 0, len(items))
	for _, item := range items {
		result = append(result, assistantmodel.AssistantFeedbackReasonSummary{
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
