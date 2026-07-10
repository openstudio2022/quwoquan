package application

import "strings"

func normalize(raw string) string {
	return strings.ToLower(strings.TrimSpace(raw))
}

func anyInt(value any) (int, bool) {
	switch v := value.(type) {
	case int:
		return v, true
	case int32:
		return int(v), true
	case int64:
		return int(v), true
	case float32:
		return int(v), true
	case float64:
		return int(v), true
	default:
		return 0, false
	}
}

func stringSliceFromAny(value any) []string {
	switch v := value.(type) {
	case []string:
		return cloneStrings(v)
	case []any:
		out := make([]string, 0, len(v))
		for _, item := range v {
			if text, ok := item.(string); ok && strings.TrimSpace(text) != "" {
				out = append(out, text)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}

func mapSliceFromAny(value any) []map[string]any {
	switch v := value.(type) {
	case []map[string]any:
		return cloneObjectSlice(v)
	case []any:
		out := make([]map[string]any, 0, len(v))
		for _, item := range v {
			if m, ok := item.(map[string]any); ok {
				out = append(out, cloneMap(m))
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}

func cloneHomepage(in *Homepage) Homepage {
	if in == nil {
		return Homepage{}
	}
	out := *in
	out.CategoryTags = cloneStrings(in.CategoryTags)
	out.Location = cloneGeoPoint(in.Location)
	out.ReviewSummary = cloneMap(in.ReviewSummary)
	out.ContentPreview = cloneObjectSlice(in.ContentPreview)
	out.QuestionPreview = cloneObjectSlice(in.QuestionPreview)
	out.RelatedGroups = cloneObjectSlice(in.RelatedGroups)
	out.RelationEdges = cloneObjectSlice(in.RelationEdges)
	out.AssistantContext = cloneMap(in.AssistantContext)
	out.IntroductionAssets = cloneIntroductionAssets(in.IntroductionAssets)
	return out
}

func cloneIntroductionAssets(assets []HomepageIntroductionAsset) []HomepageIntroductionAsset {
	if len(assets) == 0 {
		return nil
	}
	out := make([]HomepageIntroductionAsset, len(assets))
	copy(out, assets)
	return out
}

func coverURLFromIntroductionAssets(assets []HomepageIntroductionAsset) string {
	for _, asset := range assets {
		if asset.Role == introductionAssetRoleCover && strings.TrimSpace(asset.URL) != "" {
			return strings.TrimSpace(asset.URL)
		}
	}
	return ""
}

func (s *HomepageService) applyViewerFollowStateLocked(homepage *Homepage, viewerID string) {
	if homepage == nil {
		return
	}
	followers := s.followers[homepage.ID]
	homepage.FollowerCount = len(followers)
	viewerID = strings.TrimSpace(viewerID)
	homepage.ViewerFollows = viewerID != "" && followers != nil && followers[viewerID]
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	out := make([]string, len(values))
	copy(out, values)
	return out
}

func cloneGeoPoint(point *GeoPoint) *GeoPoint {
	if point == nil {
		return nil
	}
	out := *point
	return &out
}

func cloneMap(in map[string]any) map[string]any {
	if len(in) == 0 {
		return nil
	}
	out := make(map[string]any, len(in))
	for key, value := range in {
		out[key] = value
	}
	return out
}

func cloneObjectSlice(items []map[string]any) []map[string]any {
	if len(items) == 0 {
		return nil
	}
	out := make([]map[string]any, len(items))
	for i := range items {
		out[i] = cloneMap(items[i])
	}
	return out
}
