package orchestration

import (
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
)

// topInterestTags returns up to limit trimmed interest tag refs (priority order)
// from the profile, deduped. Used to seed personalized prompts/copy.
func topInterestTags(profile *ports.ProactiveInterestProfile, limit int) []string {
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
