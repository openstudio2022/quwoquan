// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package recommendation

import (
	"context"
	"errors"
	"testing"
	"time"
)

var errSequentialRecommendationRead = errors.New(
	"sequential recommendation Redis read is forbidden",
)

// pipelineOnlyReadRedis proves that every multi-read feed path uses
// PipelineRead. Command writes remain available through the embedded fake, but
// any sequential read fails the test immediately.
type pipelineOnlyReadRedis struct {
	*mockRedisClient
}

func (r *pipelineOnlyReadRedis) HGetAll(
	context.Context,
	string,
) (map[string]string, error) {
	return nil, errSequentialRecommendationRead
}

func (r *pipelineOnlyReadRedis) SMembers(
	context.Context,
	string,
) ([]string, error) {
	return nil, errSequentialRecommendationRead
}

func (r *pipelineOnlyReadRedis) SIsMember(
	context.Context,
	string,
	string,
) (bool, error) {
	return false, errSequentialRecommendationRead
}

func seedCanonicalPipelineFixture(
	t *testing.T,
	hotPath *HotPath,
	at time.Time,
) {
	t.Helper()
	ctx := context.Background()
	if err := hotPath.RecordServed(
		ctx,
		"u1",
		[]FeedItem{{ContentID: "c_served"}},
		at,
	); err != nil {
		t.Fatalf("record served: %v", err)
	}
	if err := hotPath.RecordImpressed(
		ctx,
		"u1",
		"c_impressed",
		at,
	); err != nil {
		t.Fatalf("record impressed: %v", err)
	}
	for _, signal := range []BehaviorSignal{
		{
			UserID: "u1", SessionID: "s1", ContentID: "c_neg",
			Action: "dislike",
		},
		{
			UserID: "u1", SessionID: "s1", ContentID: "c_hidden_author",
			Action: "hide_author", AuthorID: "author-hidden",
		},
		{
			UserID: "u1", SessionID: "s1", ContentID: "c_hidden_type",
			Action: "hide_content_type", ContentType: "video",
		},
		{
			UserID: "u1", SessionID: "s1", ContentID: "c_interest",
			Action: "click", Tags: []string{"Topic/旅行"},
		},
	} {
		if err := hotPath.ProcessSignal(ctx, signal); err != nil {
			t.Fatalf("process %s: %v", signal.Action, err)
		}
	}
}

func canonicalFilterFixtureCandidates() []ContentCandidate {
	return []ContentCandidate{
		{ContentID: "c_neg"},
		{ContentID: "c_served"},
		{ContentID: "c_impressed"},
		{ContentID: ""},
		{ContentID: "c_ok"},
	}
}

func TestHotPathMultiReadsUseOnlyCanonicalPipeline(t *testing.T) {
	ctx := context.Background()
	at := time.Now().UTC()
	redis := &pipelineOnlyReadRedis{mockRedisClient: newMockRedis()}
	hotPath := NewHotPath(redis)
	seedCanonicalPipelineFixture(t, hotPath, at)

	session, err := hotPath.GetSessionState(ctx, "u1", "s1")
	if err != nil {
		t.Fatalf("pipeline session state: %v", err)
	}
	if session.TagWeights["Topic/旅行"] <= 0 {
		t.Fatalf("pipeline session state lost tag weights: %+v", session)
	}

	exclusions, err := hotPath.LoadHardExclusions(ctx, "u1")
	if err != nil {
		t.Fatalf("pipeline hard exclusions: %v", err)
	}
	if !exclusions.NegativeContentIDs["c_neg"] ||
		!exclusions.HiddenAuthors["author-hidden"] ||
		!exclusions.HiddenContentTypes["video"] {
		t.Fatalf("pipeline hard exclusions incomplete: %+v", exclusions)
	}

	filtered, err := hotPath.FilterCandidates(
		ctx,
		"u1",
		canonicalFilterFixtureCandidates(),
		at,
	)
	if err != nil {
		t.Fatalf("pipeline exposure filter: %v", err)
	}
	if len(filtered) != 1 || filtered[0].ContentID != "c_ok" {
		t.Fatalf("pipeline filter result=%+v, want only c_ok", filtered)
	}

	relaxed, err := hotPath.FilterCandidatesRelaxedExposure(
		ctx,
		"u1",
		canonicalFilterFixtureCandidates(),
		at,
	)
	if err != nil {
		t.Fatalf("pipeline relaxed exposure filter: %v", err)
	}
	if len(relaxed) != 3 ||
		relaxed[0].ContentID != "c_served" ||
		relaxed[1].ContentID != "c_impressed" ||
		relaxed[2].ContentID != "c_ok" {
		t.Fatalf("relaxed pipeline result=%+v", relaxed)
	}
}
