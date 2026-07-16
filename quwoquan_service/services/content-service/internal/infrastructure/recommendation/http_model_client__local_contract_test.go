package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http"
	"testing"
	"time"

	rtrec "quwoquan_service/runtime/recommendation"
	"quwoquan_service/runtime/recpolicy"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

type fixedServiceCredentials string

func (credential fixedServiceCredentials) AuthorizationHeader(context.Context) (string, error) {
	return string(credential), nil
}

func (fn roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestHTTPModelServiceClient_Predict_Unreachable(t *testing.T) {
	// No server listening on this port; client should return error.
	client, err := NewHTTPModelServiceClient(
		"http://127.0.0.1:19999",
		20*time.Millisecond,
		fixedServiceCredentials("Bearer service-token"),
	)
	if err != nil {
		t.Fatalf("create client: %v", err)
	}
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

func TestRemoteModelScorerDoesNotFallbackWhenServiceFails(t *testing.T) {
	client, err := NewHTTPModelServiceClient(
		"http://127.0.0.1:19998",
		15*time.Millisecond,
		fixedServiceCredentials("Bearer service-token"),
	)
	if err != nil {
		t.Fatalf("create client: %v", err)
	}
	remote := rtrec.NewRemoteModelScorer(client, "content_feed")

	ctx := context.Background()
	now := time.Now()
	features := &rtrec.ScoringFeatures{
		Session: &rtrec.SessionState{UserID: "u1", SessionID: "s1"},
		Weights: recpolicy.Baseline().WeightPresets["control"],
		Scorer:  recpolicy.Baseline().Scorer,
	}
	candidates := []rtrec.ContentCandidate{
		{ContentID: "c1", ContentType: "post", AuthorID: "a1", PublishedAt: now, LikeCount: 10},
	}
	if _, err := remote.ScoreBatch(ctx, features, candidates); err == nil {
		t.Fatal("remote scoring failure must surface; production cannot fall back to rule scoring")
	}
}

func TestHTTPModelServiceClient_Predict_ContractStable(t *testing.T) {
	client, err := NewHTTPModelServiceClient(
		"http://rec-model.test",
		2*time.Second,
		fixedServiceCredentials("Bearer service-token"),
	)
	if err != nil {
		t.Fatalf("create client: %v", err)
	}
	client.httpClient.Transport = roundTripFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method != http.MethodPost {
			t.Fatalf("expected POST, got %s", r.Method)
		}
		if r.URL.Path != "/internal/v1/recommendation/model-releases:score" {
			t.Fatalf("unexpected generated scoring path: %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer service-token" {
			t.Fatalf("missing service authorization: %q", r.Header.Get("Authorization"))
		}

		var req rtrec.ModelPredictRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			t.Fatalf("decode request: %v", err)
		}
		if req.Scenario != "content_feed" || req.UserID != "u1" || req.SessionID != "s1" {
			t.Fatalf("unexpected request fields: %+v", req)
		}
		if len(req.Candidates) != 1 || req.Candidates[0].ContentID != "c1" {
			t.Fatalf("unexpected candidates: %+v", req.Candidates)
		}
		return &http.Response{
			StatusCode: http.StatusOK,
			Header:     http.Header{"Content-Type": []string{"application/json"}},
			Body:       io.NopCloser(bytes.NewReader([]byte(`{"scores":[{"contentId":"c1","score":0.93}]}`))),
		}, nil
	})
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
