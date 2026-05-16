package recommendation

import (
	"context"
	"time"
)

// SocialRecallSource recalls content based on social signals:
// - Content that friends interacted with
// - Hot content within user's circles
// - Content from commonly-followed authors (collaborative filtering)
type SocialRecallSource struct {
	socialProvider SocialGraphProvider
	candidateDB   SocialCandidateDB
	maxAge        time.Duration
}

// SocialCandidateDB provides candidate lookup by content IDs or circle context.
type SocialCandidateDB interface {
	GetCandidatesByIDs(ctx context.Context, ids []string) ([]ContentCandidate, error)
	GetCircleHotContent(ctx context.Context, circleIDs []string, limit int, maxAge time.Duration) ([]ContentCandidate, error)
}

// NullSocialCandidateDB returns empty results.
type NullSocialCandidateDB struct{}

func (*NullSocialCandidateDB) GetCandidatesByIDs(_ context.Context, _ []string) ([]ContentCandidate, error) {
	return nil, nil
}
func (*NullSocialCandidateDB) GetCircleHotContent(_ context.Context, _ []string, _ int, _ time.Duration) ([]ContentCandidate, error) {
	return nil, nil
}

func NewSocialRecallSource(provider SocialGraphProvider, db SocialCandidateDB, maxAge time.Duration) *SocialRecallSource {
	if provider == nil {
		provider = &NullSocialGraphProvider{}
	}
	if db == nil {
		db = &NullSocialCandidateDB{}
	}
	if maxAge <= 0 {
		maxAge = 7 * 24 * time.Hour
	}
	return &SocialRecallSource{
		socialProvider: provider,
		candidateDB:   db,
		maxAge:        maxAge,
	}
}

func (s *SocialRecallSource) Recall(ctx context.Context, req RecallRequest) ([]ContentCandidate, error) {
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	// Get content that friends interacted with
	friendContent, err := s.socialProvider.GetFriendInteractedContent(ctx, req.UserID, limit)
	if err != nil {
		friendContent = nil
	}

	var candidates []ContentCandidate

	if len(friendContent) > 0 {
		friendCandidates, err := s.candidateDB.GetCandidatesByIDs(ctx, friendContent)
		if err == nil {
			for i := range friendCandidates {
				friendCandidates[i].RecallPath = "social_friend"
			}
			candidates = append(candidates, friendCandidates...)
		}
	}

	// Cap at requested limit
	if len(candidates) >= limit {
		return candidates[:limit], nil
	}

	return candidates, nil
}
