// spec_ref: specs/feature-tree/runtime/runtime-recommendation/spec.md#sit-001
package recommendation

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"
)

type terminalRecallSource struct {
	candidates []ContentCandidate
	err        error
}

func (s terminalRecallSource) Recall(context.Context, RecallRequest) ([]ContentCandidate, error) {
	return append([]ContentCandidate(nil), s.candidates...), s.err
}

type terminalEmptyScorer struct{}

func (terminalEmptyScorer) ScoreBatch(
	context.Context,
	*ScoringFeatures,
	[]ContentCandidate,
) ([]ScoredCandidate, error) {
	return nil, nil
}

type terminalCanonicalLowScorer struct{}

func (terminalCanonicalLowScorer) ScoreBatch(
	_ context.Context,
	_ *ScoringFeatures,
	candidates []ContentCandidate,
) ([]ScoredCandidate, error) {
	scored := make([]ScoredCandidate, 0, len(candidates))
	for _, candidate := range candidates {
		score := 100.0
		if candidate.SourceOwner == "qwq_data" {
			score = 0.01
		}
		scored = append(scored, ScoredCandidate{Candidate: candidate, Score: score})
	}
	return scored, nil
}

type terminalSessionReader struct {
	hard    FeedbackExclusions
	hardErr error
	session *SessionState
	sessErr error
}

func (reader terminalSessionReader) LoadHardExclusions(
	context.Context,
	string,
) (FeedbackExclusions, error) {
	return reader.hard, reader.hardErr
}

func (reader terminalSessionReader) GetSessionState(
	context.Context,
	string,
	string,
) (*SessionState, error) {
	if reader.session == nil {
		reader.session = &SessionState{}
	}
	return reader.session, reader.sessErr
}

type terminalExposureFilter struct {
	err error
}

type terminalCanonicalDroppingPreRanker struct{}

func (terminalCanonicalDroppingPreRanker) PreRank(
	_ context.Context,
	candidates []ContentCandidate,
	limit int,
) []ContentCandidate {
	selected := make([]ContentCandidate, 0, len(candidates))
	for _, candidate := range candidates {
		if candidate.SourceOwner == "qwq_data" {
			continue
		}
		selected = append(selected, candidate)
		if len(selected) == limit {
			break
		}
	}
	return selected
}

func (filter terminalExposureFilter) FilterCandidates(
	context.Context,
	string,
	[]ContentCandidate,
	time.Time,
) ([]ContentCandidate, error) {
	return nil, filter.err
}

func TestEngineInitialRecommendRecallTerminalSemantics(t *testing.T) {
	ctx := context.Background()
	hp := NewHotPath(newMockRedis())
	candidate := ContentCandidate{ContentID: "post-1", ContentType: "image", AuthorID: "author-1"}

	tests := []struct {
		name        string
		sources     []CandidateSource
		wantStage   FailureStage
		wantItems   int
		wantOutcome FeedTerminalOutcome
	}{
		{
			name:      "all applicable sources failed",
			sources:   []CandidateSource{terminalRecallSource{err: fmt.Errorf("mongo unavailable")}},
			wantStage: FailureStageRecallAllFailed,
		},
		{
			name: "partial source failure with healthy empty",
			sources: []CandidateSource{
				terminalRecallSource{err: fmt.Errorf("source unavailable")},
				terminalRecallSource{},
			},
			wantStage: FailureStageRecallPartialFailedEmpty,
		},
		{
			name: "partial source failure with candidates degrades",
			sources: []CandidateSource{
				terminalRecallSource{err: fmt.Errorf("source unavailable")},
				terminalRecallSource{candidates: []ContentCandidate{candidate}},
			},
			wantItems:   1,
			wantStage:   FailureStageRecallPartialFailed,
			wantOutcome: FeedTerminalDegraded,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			engine := NewEngine(hp, test.sources, WithPolicyStore(noExplorePolicyStore()))
			resp, err := engine.GetFeed(ctx, GetFeedRequest{
				UserID: "u-terminal", SessionID: "s-terminal",
				FeedType: FeedDiscovery, Sort: FeedSortRecommend, Limit: 10,
				DeferDeliveryAccounting: true,
			})
			if test.wantItems == 0 {
				if got := FailureStageOf(err); got != test.wantStage {
					t.Fatalf("failure stage = %q, want %q (err=%v)", got, test.wantStage, err)
				}
				return
			}
			if err != nil {
				t.Fatalf("GetFeed: %v", err)
			}
			if len(resp.Items) != test.wantItems {
				t.Fatalf("items = %d, want %d", len(resp.Items), test.wantItems)
			}
			if resp.TerminalOutcome != test.wantOutcome || resp.FailureStage != test.wantStage {
				t.Fatalf("terminal = (%q,%q), want (%q,%q)",
					resp.TerminalOutcome, resp.FailureStage, test.wantOutcome, test.wantStage)
			}
		})
	}
}

func TestEnginePremiumInitialHealthyEmptyIsCanonicalEmpty(t *testing.T) {
	engine := NewEngine(NewHotPath(newMockRedis()), nil, WithPolicyStore(noExplorePolicyStore()))
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-premium-empty", FeedType: FeedSimilar, Surface: "premium_stream",
		Sort: FeedSortRecommend, Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if len(response.Items) != 0 || response.TerminalOutcome != FeedTerminalEmpty ||
		response.FailureStage != FailureStageNone || response.PolicyDigest == "" {
		t.Fatalf("unexpected healthy empty terminal: %+v", response)
	}
}

func TestEngineBindsCanonicalDataCandidatesToActiveRelease(t *testing.T) {
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{
			{
				ContentID: "post-stale", ContentType: "image", AuthorID: "author-stale",
				SupplySource: "data_engineering", SourceOwner: "qwq_data",
				ReleaseID: "rel_previous", LifecycleStatus: "active",
			},
			{
				ContentID: "post-active", ContentType: "video", AuthorID: "author-active",
				SupplySource: "data_engineering", SourceOwner: "qwq_data",
				ReleaseID: "rel_current", LifecycleStatus: "active",
			},
			{
				ContentID: "post-ugc", ContentType: "image", AuthorID: "author-ugc",
				SupplySource: "ugc",
			},
		}}},
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-release-bound", FeedType: FeedDiscovery, Sort: FeedSortRecommend,
		ActiveReleaseID: "rel_current", Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	ids := make(map[string]bool, len(response.Items))
	for _, item := range response.Items {
		ids[item.ContentID] = true
	}
	if ids["post-stale"] || !ids["post-active"] || !ids["post-ugc"] {
		t.Fatalf("release-bound candidates mismatch: %+v", response.Items)
	}
}

func TestEngineRetainsActiveReleaseAnchorAcrossQuotaAndPreRank(t *testing.T) {
	candidates := make([]ContentCandidate, 0, 32)
	for i := 0; i < 31; i++ {
		candidates = append(candidates, ContentCandidate{
			ContentID: fmt.Sprintf("post-ugc-%02d", i), ContentType: "image",
			AuthorID: fmt.Sprintf("author-ugc-%02d", i), SupplySource: "ugc",
		})
	}
	candidates = append(candidates, ContentCandidate{
		ContentID: "post-active", ContentType: "video", AuthorID: "author-active",
		SupplySource: "data_engineering", SourceOwner: "qwq_data",
		ReleaseID: "rel_current", LifecycleStatus: "active",
	})

	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: candidates}},
		WithPreRanker(terminalCanonicalDroppingPreRanker{}),
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-release-anchor", FeedType: FeedDiscovery, Sort: FeedSortRecommend,
		ActiveReleaseID: "rel_current", Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	found := false
	for _, item := range response.Items {
		if item.ContentID == "post-active" && item.ReleaseID == "rel_current" {
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("active release anchor missing from initial page: %+v", response.Items)
	}
}

func TestEngineReservesInitialPageSlotForEligibleLowScoreActiveRelease(t *testing.T) {
	const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	candidates := make([]ContentCandidate, 0, 31)
	for i := 0; i < 30; i++ {
		candidates = append(candidates, ContentCandidate{
			ContentID: fmt.Sprintf("post-ugc-%02d", i), ContentType: "image",
			AuthorID: fmt.Sprintf("author-ugc-%02d", i), SupplySource: "ugc",
		})
	}
	candidates = append(candidates, ContentCandidate{
		ContentID: "post-active-low-score", ContentType: "video", AuthorID: "author-active",
		SupplySource: "data_engineering", SourceOwner: "qwq_data",
		ReleaseID: "rel_current", ManifestDigest: digest, LifecycleStatus: "active",
	})

	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: candidates}},
		WithScorer(terminalCanonicalLowScorer{}),
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-low-score-anchor", FeedType: FeedDiscovery, Sort: FeedSortRecommend,
		ActiveReleaseID: "rel_current", ActiveManifestDigest: digest,
		Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if len(response.Items) != 10 {
		t.Fatalf("initial page items = %d, want 10", len(response.Items))
	}
	if !responseHasContentID(response, "post-active-low-score") {
		t.Fatalf("eligible active-release anchor missing from initial page: %+v", response.Items)
	}
}

func TestEngineRejectsWrongDigestAndKeepsMatchingDigestAnchor(t *testing.T) {
	const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{
			{
				ContentID: "post-wrong-digest", ContentType: "video", AuthorID: "author-wrong",
				SourceOwner: "qwq_data", SupplySource: "data_engineering",
				ReleaseID:       "rel_current",
				ManifestDigest:  "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
				LifecycleStatus: "active", ViewCount: 100000,
			},
			{
				ContentID: "post-matching-digest", ContentType: "video", AuthorID: "author-match",
				SourceOwner: "qwq_data", SupplySource: "data_engineering",
				ReleaseID: "rel_current", ManifestDigest: digest,
				LifecycleStatus: "active",
			},
		}}},
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-digest-anchor", FeedType: FeedDiscovery, Sort: FeedSortRecommend,
		ActiveReleaseID: "rel_current", ActiveManifestDigest: digest,
		Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if responseHasContentID(response, "post-wrong-digest") ||
		!responseHasContentID(response, "post-matching-digest") {
		t.Fatalf("digest-bound candidates mismatch: %+v", response.Items)
	}
}

func TestEngineDoesNotRestoreHardExcludedActiveReleaseAnchor(t *testing.T) {
	const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	hard := emptyFeedbackExclusions()
	hard.NegativeContentIDs["post-active-blocked"] = true
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{
			{ContentID: "post-ugc", ContentType: "image", AuthorID: "author-ugc", SupplySource: "ugc"},
			{
				ContentID: "post-active-blocked", ContentType: "video", AuthorID: "author-active",
				SourceOwner: "qwq_data", SupplySource: "data_engineering",
				ReleaseID: "rel_current", ManifestDigest: digest, LifecycleStatus: "active",
			},
		}}},
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-hard-anchor", FeedType: FeedDiscovery, Sort: FeedSortRecommend,
		ActiveReleaseID: "rel_current", ActiveManifestDigest: digest,
		FeedbackExclusions: &hard, Limit: 10, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if len(response.Items) != 0 || response.TerminalOutcome != FeedTerminalEmpty ||
		response.FailureStage != FailureStageNone {
		t.Fatalf("hard-excluded active anchor must be a healthy empty result: %+v", response)
	}
}

func responseHasContentID(response *FeedResponse, contentID string) bool {
	if response == nil {
		return false
	}
	for _, item := range response.Items {
		if item.ContentID == contentID {
			return true
		}
	}
	return false
}

func TestEngineHardExclusionUnavailableFailsClosed(t *testing.T) {
	engine := NewEngine(
		terminalSessionReader{hardErr: fmt.Errorf("redis unavailable")},
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{{ContentID: "post-1"}}}},
		WithPolicyStore(noExplorePolicyStore()),
	)
	_, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-hard-fail", FeedType: FeedDiscovery, Sort: FeedSortRecommend, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if got := FailureStageOf(err); got != FailureStageHardExclusionStateUnavailable {
		t.Fatalf("hard exclusion error stage = %q, want %q (err=%v)", got, FailureStageHardExclusionStateUnavailable, err)
	}
}

func TestEngineSoftRedisReadsDegradeWithoutBypassingHardExclusions(t *testing.T) {
	hard := emptyFeedbackExclusions()
	hard.NegativeContentIDs["post-blocked"] = true
	reader := terminalSessionReader{
		hard:    hard,
		sessErr: fmt.Errorf("session personalization unavailable"),
	}
	engine := NewEngine(
		reader,
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{
			{ContentID: "post-blocked", ContentType: "image", AuthorID: "author-blocked"},
			{ContentID: "post-allowed", ContentType: "image", AuthorID: "author-allowed"},
		}}},
		WithExposureGovernance(nil, terminalExposureFilter{err: fmt.Errorf("exposure memory unavailable")}),
		WithPolicyStore(noExplorePolicyStore()),
	)
	response, err := engine.GetFeed(context.Background(), GetFeedRequest{
		UserID: "u-soft-degrade", FeedType: FeedDiscovery, Sort: FeedSortRecommend, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("soft Redis dependency must degrade: %v", err)
	}
	if len(response.Items) != 1 || response.Items[0].ContentID != "post-allowed" {
		t.Fatalf("hard exclusion must survive soft degradation: %+v", response.Items)
	}
	if response.TerminalOutcome != FeedTerminalDegraded ||
		response.FailureStage != FailureStageExposureMemoryUnavailable {
		t.Fatalf("soft degradation terminal = (%q,%q)", response.TerminalOutcome, response.FailureStage)
	}
}

func TestFailureStageRejectsUnboundedValues(t *testing.T) {
	err := NewFeedFailure(FailureStage("user-controlled-stage"), fmt.Errorf("boom"))
	if err.Stage != FailureStageNone || FailureStageOf(err) != FailureStageNone {
		t.Fatalf("unbounded failure stage must normalize to none: %+v", err)
	}
}

func TestEngineScorerErrorAndEmptyOutputAreTypedFailures(t *testing.T) {
	ctx := context.Background()
	hp := NewHotPath(newMockRedis())
	source := terminalRecallSource{candidates: []ContentCandidate{{
		ContentID: "post-score", ContentType: "image", AuthorID: "author-score",
	}}}

	errorEngine := NewEngine(
		hp,
		[]CandidateSource{source},
		WithScorer(&failingModelScorer{}),
		WithPolicyStore(noExplorePolicyStore()),
	)
	_, err := errorEngine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-score-error", FeedType: FeedDiscovery, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if got := FailureStageOf(err); got != FailureStageScorerUnavailable {
		t.Fatalf("scorer error stage = %q, want %q (err=%v)", got, FailureStageScorerUnavailable, err)
	}

	emptyEngine := NewEngine(
		hp,
		[]CandidateSource{source},
		WithScorer(terminalEmptyScorer{}),
		WithPolicyStore(noExplorePolicyStore()),
	)
	_, err = emptyEngine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-score-empty", FeedType: FeedDiscovery, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if got := FailureStageOf(err); got != FailureStageScorerEmptyOutput {
		t.Fatalf("scorer empty stage = %q, want %q (err=%v)", got, FailureStageScorerEmptyOutput, err)
	}
}

func TestEngineHealthyFollowingEmptyAndMissingWindowFailsClosed(t *testing.T) {
	ctx := context.Background()
	engine := NewEngine(NewHotPath(newMockRedis()), nil, WithPolicyStore(noExplorePolicyStore()))

	following, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-follow-empty", FeedType: FeedFollow, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil || len(following.Items) != 0 || following.TerminalOutcome != FeedTerminalEmpty {
		t.Fatalf("healthy following empty terminal mismatch: resp=%+v err=%v", following, err)
	}

	_, err = engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-follow-continuation", SessionID: "s-follow-continuation",
		FeedType: FeedFollow, Sort: FeedSortRecommend, Limit: 10,
		FeedRequestID: "frq_missing_window",
		Continuation: &RankedFeedContinuation{
			WindowID: "rfw_missing", AfterOrdinal: 1, AfterContentID: "post_missing",
			ExpiresAt: time.Now().Add(time.Minute),
		},
		DeferDeliveryAccounting: true,
	})
	if !errors.Is(err, ErrInvalidFeedCursor) {
		t.Fatalf("missing immutable window error = %v, want ErrInvalidFeedCursor", err)
	}

}

func TestEngineRejectsContinuationCursorAfterActiveReleaseSwitch(t *testing.T) {
	ctx := context.Background()
	const oldDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	const newDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

	for _, feedType := range []FeedType{FeedDiscovery, FeedSimilar} {
		t.Run(string(feedType), func(t *testing.T) {
			hotPath := NewHotPath(newMockRedis())
			engine := NewEngine(hotPath, []CandidateSource{terminalRecallSource{candidates: []ContentCandidate{
				{
					ContentID: "post-old-release-1", ContentType: "image", AuthorID: "author-old-1",
					SourceOwner: "qwq_data", SupplySource: "data_engineering",
					ReleaseID: "rel-old", ManifestDigest: oldDigest, LifecycleStatus: "active",
				},
				{
					ContentID: "post-old-release-2", ContentType: "video", AuthorID: "author-old-2",
					SourceOwner: "qwq_data", SupplySource: "data_engineering",
					ReleaseID: "rel-old", ManifestDigest: oldDigest, LifecycleStatus: "active",
				},
			}}}, WithPolicyStore(noExplorePolicyStore()))
			initial, initialErr := engine.GetFeed(ctx, GetFeedRequest{
				UserID: "u-release-switch", SessionID: "s-release-switch",
				RankedWindowSubjectID: "actor\x00u-release-switch",
				FeedType:              feedType, Sort: FeedSortRecommend, Limit: 1,
				FeedRequestID:   "frq_release_switch",
				ActiveReleaseID: "rel-old", ActiveManifestDigest: oldDigest,
				DeferDeliveryAccounting: true,
			})
			if initialErr != nil || initial.NextContinuation == nil {
				t.Fatalf("create old-release ranked window: response=%+v err=%v", initial, initialErr)
			}
			_, err := engine.GetFeed(ctx, GetFeedRequest{
				UserID: "u-release-switch", SessionID: "s-release-switch",
				RankedWindowSubjectID: "actor\x00u-release-switch",
				FeedType:              feedType, Sort: FeedSortRecommend, Limit: 1,
				FeedRequestID: "frq_release_switch", Continuation: initial.NextContinuation,
				ActiveReleaseID: "rel-new", ActiveManifestDigest: newDigest,
				DeferDeliveryAccounting: true,
			})
			if !errors.Is(err, ErrInvalidFeedCursor) {
				t.Fatalf("release-switch continuation error = %v, want ErrInvalidFeedCursor", err)
			}
		})
	}
}

func TestEngineInitialExposureFallbackRelaxesOnlyLongTermExposure(t *testing.T) {
	ctx := context.Background()
	hp := NewHotPath(newMockRedis())
	candidate := ContentCandidate{
		ContentID: "post-exposed", ContentType: "image", AuthorID: "author-exposed",
	}
	if err := hp.RecordServed(ctx, "u-exposure", []FeedItem{{ContentID: candidate.ContentID}}, time.Now()); err != nil {
		t.Fatalf("RecordServed: %v", err)
	}
	engine := NewEngine(
		hp,
		[]CandidateSource{terminalRecallSource{candidates: []ContentCandidate{candidate}}},
		WithExposureGovernance(hp, hp),
		WithPolicyStore(noExplorePolicyStore()),
	)
	resp, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-exposure", FeedType: FeedDiscovery, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("GetFeed: %v", err)
	}
	if len(resp.Items) != 1 || resp.Items[0].ContentID != candidate.ContentID {
		t.Fatalf("long-term exposure fallback item mismatch: %+v", resp.Items)
	}
	if resp.TerminalOutcome != FeedTerminalDegraded ||
		resp.FailureStage != FailureStageExposureExhausted {
		t.Fatalf("fallback terminal mismatch: (%q,%q)", resp.TerminalOutcome, resp.FailureStage)
	}

	if err := hp.RecordNegative(ctx, "u-exposure", candidate.ContentID); err != nil {
		t.Fatalf("RecordNegative: %v", err)
	}
	emptyResponse, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-exposure", FeedType: FeedDiscovery, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("negative-filtered GetFeed: %v", err)
	}
	if len(emptyResponse.Items) != 0 || emptyResponse.TerminalOutcome != FeedTerminalEmpty {
		t.Fatalf("explicit negative must not be bypassed: %+v", emptyResponse)
	}
}
