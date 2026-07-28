// spec_ref: specs/feature-tree/runtime/runtime-recommendation/spec.md#sit-001
package recommendation

import (
	"context"
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

func TestEngineHealthyFollowingAndValidContinuationMayEndEmpty(t *testing.T) {
	ctx := context.Background()
	engine := NewEngine(NewHotPath(newMockRedis()), nil, WithPolicyStore(noExplorePolicyStore()))

	following, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-follow-empty", FeedType: FeedFollow, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil || len(following.Items) != 0 || following.TerminalOutcome != FeedTerminalEmpty {
		t.Fatalf("healthy following empty terminal mismatch: resp=%+v err=%v", following, err)
	}

	cursor := encodeFeedCursor(feedCursorState{
		Version: 1, SessionID: "s-continuation", Offset: 10,
		ExpiresAt: time.Now().Add(time.Minute).Unix(),
	})
	continuation, err := engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-continuation", SessionID: "s-continuation",
		FeedType: FeedDiscovery, Sort: FeedSortRecommend, Cursor: cursor, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if err != nil || len(continuation.Items) != 0 || continuation.TerminalOutcome != FeedTerminalEmpty {
		t.Fatalf("valid continuation end mismatch: resp=%+v err=%v", continuation, err)
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
	_, err = engine.GetFeed(ctx, GetFeedRequest{
		UserID: "u-exposure", FeedType: FeedDiscovery, Limit: 10,
		DeferDeliveryAccounting: true,
	})
	if got := FailureStageOf(err); got != FailureStageExposureExhausted {
		t.Fatalf("explicit negative must not be bypassed, stage=%q err=%v", got, err)
	}
}
