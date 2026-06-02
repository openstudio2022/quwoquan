package application

import (
	"context"
	"strings"
)

// ProactiveInterest is one ranked interest entry fed into proactive
// personalization. It mirrors a single rm_user_profile_view.interestProfile
// top interest, but is an assistant-domain type (cross-service Go types are
// never shared) so the user-service DTO can evolve independently.
type ProactiveInterest struct {
	TagRef    string
	Dimension string
	Score     float64
	Level     int
}

// ProactiveInterestProfile is the assistant-domain view of a user's derived
// interest profile, sourced from user-service rm_user_profile_view via the
// ProactiveInterestReader port. It carries only what proactive personalization
// needs (top interests + dimension tops + lifecycle + segments).
type ProactiveInterestProfile struct {
	TopInterests   []ProactiveInterest
	DimensionTops  map[string][]string
	LifecycleStage string
	FreshnessDays  int
	Segments       []string
}

// ProactiveInterestReader reads a user's derived interest profile for proactive
// personalization. Implemented by infrastructure (HTTP to user-service's
// GET /v1/users/{userId}/interest-profile). A nil profile (with nil error)
// means "no profile available"; callers degrade to non-personalized output.
type ProactiveInterestReader interface {
	GetInterestProfile(ctx context.Context, userID string) (*ProactiveInterestProfile, error)
}

// topInterestTags returns up to limit trimmed interest tag refs (priority order)
// from the profile, deduped. Used to seed personalized prompts/copy.
func topInterestTags(profile *ProactiveInterestProfile, limit int) []string {
	if profile == nil || limit <= 0 {
		return nil
	}
	out := make([]string, 0, limit)
	seen := map[string]bool{}
	for _, interest := range profile.TopInterests {
		tag := strings.TrimSpace(interest.TagRef)
		if tag == "" || seen[tag] {
			continue
		}
		seen[tag] = true
		out = append(out, tag)
		if len(out) >= limit {
			break
		}
	}
	return out
}
