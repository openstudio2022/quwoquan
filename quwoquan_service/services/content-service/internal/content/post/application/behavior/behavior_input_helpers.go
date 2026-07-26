package behavior

import (
	"strings"

	rtrec "quwoquan_service/runtime/recommendation"
	post "quwoquan_service/services/content-service/generated/content/post"
)

// supportedBehaviorActions derives from SignalWeights (single source of truth
// aligned with behaviors.yaml signal_weight). An action is supported iff it
// has a weight entry, preventing silent drift between the two maps.
var supportedBehaviorActions = func() map[string]struct{} {
	m := make(map[string]struct{}, len(rtrec.SignalWeights))
	for action := range rtrec.SignalWeights {
		m[action] = struct{}{}
	}
	return m
}()

// intersectionFeedbackKindSupported 校验 feedbackKind ∈ registry.feedbackKinds 闭集
// （codegen 单一真相源 post.IntersectionFeedbackKinds），端上报与云侧消费同源。
func intersectionFeedbackKindSupported(kind string) bool {
	for _, k := range post.IntersectionFeedbackKinds {
		if k == kind {
			return true
		}
	}
	return false
}

func isWishlistAction(action string) bool {
	return action == "wishlist_add" || action == "wishlist_remove"
}

// authorImpactActionRequiresPost is deliberately narrow. These actions have a
// canonical Post at this boundary, so author/tag facts can be resolved without
// trusting the client. Social/circle/assistant actions are projected by their
// owning confirmed-command outboxes instead of this generic behavior endpoint.
func authorImpactActionRequiresPost(action string) bool {
	switch strings.TrimSpace(action) {
	case "author_view", "comment", "content_depth", "like", "play_progress", "share":
		return true
	default:
		return false
	}
}

func normalizeBehaviorAction(input BehaviorEventInput) string {
	return strings.TrimSpace(strings.ToLower(input.Action))
}

func firstString(values []string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func behaviorTagsFromAny(v any) []string {
	switch vv := v.(type) {
	case []string:
		return vv
	case []any:
		out := make([]string, 0, len(vv))
		for _, item := range vv {
			if s, ok := item.(string); ok && strings.TrimSpace(s) != "" {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

// canonicalOnboardingTagRefs is deliberately narrow: onboarding preferences
// are path-based taxonomy references, and duplicated or whitespace-only paths
// must not increase a user's first-session recommendation weight twice.
func canonicalOnboardingTagRefs(tagRefs []string) []string {
	seen := make(map[string]struct{}, len(tagRefs))
	canonical := make([]string, 0, len(tagRefs))
	for _, tagRef := range tagRefs {
		normalized := strings.TrimSpace(tagRef)
		if normalized == "" {
			continue
		}
		if _, exists := seen[normalized]; exists {
			continue
		}
		seen[normalized] = struct{}{}
		canonical = append(canonical, normalized)
	}
	return canonical
}
