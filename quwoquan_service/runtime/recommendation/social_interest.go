package recommendation

import "context"

// SocialGraphProvider supplies social signal data for interest mining.
type SocialGraphProvider interface {
	// GetUserCircleTags returns aggregated tags from circles the user belongs to.
	GetUserCircleTags(ctx context.Context, userID string) (map[string]float64, error)
	// GetFriendInterestIntersection returns shared interest tags from followed users.
	GetFriendInterestIntersection(ctx context.Context, userID string) (map[string]float64, error)
	// GetFriendInteractedContent returns contentIDs that followed users interacted with.
	GetFriendInteractedContent(ctx context.Context, userID string, limit int) ([]string, error)
	// GetUserCircleIDs returns the IDs of circles the user belongs to.
	GetUserCircleIDs(ctx context.Context, userID string) ([]string, error)
}

// NullSocialGraphProvider returns empty social signals.
type NullSocialGraphProvider struct{}

func (*NullSocialGraphProvider) GetUserCircleTags(_ context.Context, _ string) (map[string]float64, error) {
	return nil, nil
}
func (*NullSocialGraphProvider) GetFriendInterestIntersection(_ context.Context, _ string) (map[string]float64, error) {
	return nil, nil
}
func (*NullSocialGraphProvider) GetFriendInteractedContent(_ context.Context, _ string, _ int) ([]string, error) {
	return nil, nil
}
func (*NullSocialGraphProvider) GetUserCircleIDs(_ context.Context, _ string) ([]string, error) {
	return nil, nil
}

// SocialInterestVector aggregates social signals for recommendation scoring.
type SocialInterestVector struct {
	// Tags propagated from user's circles (weight attenuated by 0.3x)
	CircleTagAffinities map[string]float64
	// Tags from friends' shared interests (weight attenuated by 0.5x)
	FriendTagIntersection map[string]float64
	// Combined social interest density score
	SocialDensity float64
}

// SocialInterestMiner computes the SocialInterestVector for a user.
type SocialInterestMiner struct {
	provider           SocialGraphProvider
	circleDecay        float64 // default 0.3
	friendIntersectDecay float64 // default 0.5
}

func NewSocialInterestMiner(provider SocialGraphProvider) *SocialInterestMiner {
	if provider == nil {
		provider = &NullSocialGraphProvider{}
	}
	return &SocialInterestMiner{
		provider:             provider,
		circleDecay:          0.3,
		friendIntersectDecay: 0.5,
	}
}

// Mine computes the social interest vector for a given user.
func (m *SocialInterestMiner) Mine(ctx context.Context, userID string) (*SocialInterestVector, error) {
	circleTags, err := m.provider.GetUserCircleTags(ctx, userID)
	if err != nil {
		circleTags = nil
	}

	friendTags, err := m.provider.GetFriendInterestIntersection(ctx, userID)
	if err != nil {
		friendTags = nil
	}

	result := &SocialInterestVector{
		CircleTagAffinities:   make(map[string]float64, len(circleTags)),
		FriendTagIntersection: make(map[string]float64, len(friendTags)),
	}

	totalSignals := 0.0
	for tag, weight := range circleTags {
		decayed := weight * m.circleDecay
		result.CircleTagAffinities[tag] = decayed
		totalSignals += decayed
	}

	for tag, weight := range friendTags {
		decayed := weight * m.friendIntersectDecay
		result.FriendTagIntersection[tag] = decayed
		totalSignals += decayed
	}

	if len(circleTags)+len(friendTags) > 0 {
		result.SocialDensity = totalSignals / float64(len(circleTags)+len(friendTags))
	}

	return result, nil
}
