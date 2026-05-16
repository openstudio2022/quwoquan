package recommendation

import (
	"context"
	"testing"
	"time"
)

type stubSocialGraphProvider struct {
	friendContent []string
	circleIDs     []string
	circleTags    map[string]float64
	friendTags    map[string]float64
}

func (s *stubSocialGraphProvider) GetUserCircleTags(_ context.Context, _ string) (map[string]float64, error) {
	return s.circleTags, nil
}

func (s *stubSocialGraphProvider) GetUserCircleIDs(_ context.Context, _ string) ([]string, error) {
	return s.circleIDs, nil
}

func (s *stubSocialGraphProvider) GetFriendInterestIntersection(_ context.Context, _ string) (map[string]float64, error) {
	return s.friendTags, nil
}

func (s *stubSocialGraphProvider) GetFriendInteractedContent(_ context.Context, _ string, _ int) ([]string, error) {
	return s.friendContent, nil
}

type stubSocialCandidateDB struct {
	byIDs       []ContentCandidate
	circleHot   []ContentCandidate
}

func (s *stubSocialCandidateDB) GetCandidatesByIDs(_ context.Context, ids []string) ([]ContentCandidate, error) {
	var out []ContentCandidate
	idSet := make(map[string]bool, len(ids))
	for _, id := range ids {
		idSet[id] = true
	}
	for _, c := range s.byIDs {
		if idSet[c.ContentID] {
			out = append(out, c)
		}
	}
	return out, nil
}

func (s *stubSocialCandidateDB) GetCircleHotContent(_ context.Context, _ []string, limit int, _ time.Duration) ([]ContentCandidate, error) {
	if limit > len(s.circleHot) {
		limit = len(s.circleHot)
	}
	return s.circleHot[:limit], nil
}

func TestSocialRecallSource_FriendContent(t *testing.T) {
	provider := &stubSocialGraphProvider{
		friendContent: []string{"post-1", "post-2"},
	}
	db := &stubSocialCandidateDB{
		byIDs: []ContentCandidate{
			{ContentID: "post-1", ContentType: "photo", Tags: []string{"travel"}},
			{ContentID: "post-2", ContentType: "video", Tags: []string{"food"}},
		},
	}
	src := NewSocialRecallSource(provider, db, 7*24*time.Hour)

	candidates, err := src.Recall(context.Background(), RecallRequest{
		UserID: "user-1",
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(candidates) != 2 {
		t.Fatalf("expected 2 candidates, got %d", len(candidates))
	}
	for _, c := range candidates {
		if c.RecallPath != "social_friend" {
			t.Errorf("expected recall path social_friend, got %s", c.RecallPath)
		}
	}
}

func TestSocialRecallSource_CircleFallback(t *testing.T) {
	provider := &stubSocialGraphProvider{
		circleIDs: []string{"circle-a"},
	}
	db := &stubSocialCandidateDB{
		circleHot: []ContentCandidate{
			{ContentID: "circle-post-1", ContentType: "article"},
			{ContentID: "circle-post-2", ContentType: "photo"},
		},
	}
	src := NewSocialRecallSource(provider, db, 7*24*time.Hour)

	candidates, err := src.Recall(context.Background(), RecallRequest{
		UserID: "user-2",
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(candidates) != 2 {
		t.Fatalf("expected 2 circle candidates, got %d", len(candidates))
	}
	for _, c := range candidates {
		if c.RecallPath != "social_circle" {
			t.Errorf("expected recall path social_circle, got %s", c.RecallPath)
		}
	}
}

func TestSocialRecallSource_NilProviders(t *testing.T) {
	src := NewSocialRecallSource(nil, nil, 0)
	candidates, err := src.Recall(context.Background(), RecallRequest{
		UserID: "user-3",
		Limit:  5,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(candidates) != 0 {
		t.Fatalf("expected 0 candidates with nil providers, got %d", len(candidates))
	}
}

func TestSocialRecallSource_Dedup(t *testing.T) {
	provider := &stubSocialGraphProvider{
		friendContent: []string{"shared-1"},
		circleIDs:     []string{"circle-a"},
	}
	db := &stubSocialCandidateDB{
		byIDs: []ContentCandidate{
			{ContentID: "shared-1", ContentType: "photo"},
		},
		circleHot: []ContentCandidate{
			{ContentID: "shared-1", ContentType: "photo"},
			{ContentID: "circle-only", ContentType: "video"},
		},
	}
	src := NewSocialRecallSource(provider, db, 7*24*time.Hour)

	candidates, err := src.Recall(context.Background(), RecallRequest{
		UserID: "user-4",
		Limit:  10,
	})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	// shared-1 from friend + circle-only from circle (shared-1 deduped in circle)
	if len(candidates) != 2 {
		t.Fatalf("expected 2 deduplicated candidates, got %d", len(candidates))
	}
	ids := map[string]bool{}
	for _, c := range candidates {
		if ids[c.ContentID] {
			t.Errorf("duplicate candidate: %s", c.ContentID)
		}
		ids[c.ContentID] = true
	}
}
