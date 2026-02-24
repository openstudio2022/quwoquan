package recommendation

import (
	"context"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
)

func TestHTTPModelServiceClient_Predict_Unreachable(t *testing.T) {
	// No server listening on this port; client should return error.
	client := NewHTTPModelServiceClient("http://127.0.0.1:19999", 20*time.Millisecond)
	ctx := context.Background()
	req := &rtrec.ModelPredictRequest{
		Scenario:  "content_feed",
		UserID:    "u1",
		SessionID: "s1",
		Candidates: []rtrec.CandidateInput{
			{ContentID: "c1", ContentType: "post"},
		},
	}
	resp, err := client.Predict(ctx, req)
	if err == nil {
		t.Fatalf("expected error when server unreachable, got response: %+v", resp)
	}
}

func TestCascadeScorer_FallbackWhenHTTPClientFails(t *testing.T) {
	// HTTPModelServiceClient to unreachable URL → RemoteModelScorer fails → CascadeScorer falls back to RuleScorer
	client := NewHTTPModelServiceClient("http://127.0.0.1:19998", 15*time.Millisecond)
	remote := rtrec.NewRemoteModelScorer(client, "content_feed")
	rule := &rtrec.RuleScorer{}
	cascade := rtrec.NewCascadeScorer(remote, rule, 50*time.Millisecond)

	ctx := context.Background()
	now := time.Now()
	features := &rtrec.ScoringFeatures{
		Session: &rtrec.SessionState{UserID: "u1", SessionID: "s1"},
		Weights: rtrec.DefaultWeights(),
	}
	candidates := []rtrec.ContentCandidate{
		{ContentID: "c1", ContentType: "post", AuthorID: "a1", PublishedAt: now, LikeCount: 10},
	}
	scored, err := cascade.ScoreBatch(ctx, features, candidates)
	if err != nil {
		t.Fatalf("CascadeScorer should fallback to RuleScorer, not return error: %v", err)
	}
	if len(scored) != 1 {
		t.Fatalf("expected 1 scored candidate, got %d", len(scored))
	}
	if scored[0].Candidate.ContentID != "c1" {
		t.Errorf("expected content c1, got %s", scored[0].Candidate.ContentID)
	}
}
