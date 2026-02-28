package recommendation

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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

func TestHTTPModelServiceClient_Predict_ContractStable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			t.Fatalf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/v1/score" {
			t.Fatalf("expected /v1/score, got %s", r.URL.Path)
		}

		var req rtrec.ModelPredictRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if req.Scenario != "content_feed" {
			t.Fatalf("expected scenario content_feed, got %s", req.Scenario)
		}
		if req.UserID != "u1" || req.SessionID != "s1" {
			t.Fatalf("unexpected user/session: %s %s", req.UserID, req.SessionID)
		}
		if len(req.Candidates) != 1 || req.Candidates[0].ContentID != "c1" {
			t.Fatalf("unexpected candidates: %+v", req.Candidates)
		}

		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"scores": []map[string]any{
				{"contentId": "c1", "score": 0.93},
			},
		})
	}))
	defer srv.Close()

	client := NewHTTPModelServiceClient(srv.URL, 100*time.Millisecond)
	resp, err := client.Predict(context.Background(), &rtrec.ModelPredictRequest{
		Scenario:  "content_feed",
		UserID:    "u1",
		SessionID: "s1",
		Candidates: []rtrec.CandidateInput{
			{ContentID: "c1", ContentType: "post"},
		},
	})
	if err != nil {
		t.Fatalf("predict should succeed: %v", err)
	}
	if len(resp.Scores) != 1 {
		t.Fatalf("expected 1 score, got %d", len(resp.Scores))
	}
	if resp.Scores[0].ContentID != "c1" || resp.Scores[0].Score <= 0 {
		t.Fatalf("unexpected score response: %+v", resp.Scores[0])
	}
}
