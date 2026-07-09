package recommendation

import (
	"fmt"
	"math"
	"reflect"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
)

const (
	ContentVerticalGeneral           = "general"
	ContentVerticalTravelPhotography = "travel_photography"
	SupplySourceUGC                  = "ugc"
	SupplySourceDataEngineering      = "data_engineering"
)

// BuildRecommendationProjectionFields derives the recommendation-only fields
// persisted in rm_discovery_feed. Callers pass the same map they will $set into
// Mongo so UGC, bulk import, and data-engineering import share one projection
// formula and the feed read path only consumes materialized values.
func BuildRecommendationProjectionFields(payload map[string]any) bson.M {
	semanticCoverage := semanticMentionCoverage(payload)
	mediaCompleteness := mediaCompleteness(payload)
	qualityScore := projectedQualityScore(payload, semanticCoverage, mediaCompleteness)
	fields := bson.M{
		"qualityScore":            qualityScore,
		"recScore":                qualityScore,
		"contentVertical":         ResolveContentVertical(payload),
		"supplySource":            ResolveSupplySource(payload),
		"semanticMentionCoverage": semanticCoverage,
		"mediaCompleteness":       mediaCompleteness,
	}
	if hintCount := collectionLen(payload["intersectionHints"]); hintCount > 0 {
		fields["intersectionFactStrength"] = float64(hintCount)
		fields["intersectionFreshness"] = 1.0
		fields["intersectionClass"] = "fact"
		if sourceRef := firstIntersectionHintTarget(payload["intersectionHints"]); sourceRef != "" {
			fields["intersectionSourceRefTop"] = sourceRef
		}
	}
	return fields
}

func ResolveContentVertical(payload map[string]any) string {
	if raw := strings.TrimSpace(strings.ToLower(projectionString(payload["contentVertical"]))); raw != "" {
		return normalizeProjectedVertical(raw)
	}
	haystack := strings.ToLower(strings.Join(projectionTokens(payload), " "))
	switch {
	case strings.Contains(haystack, "travel"),
		strings.Contains(haystack, "旅行"),
		strings.Contains(haystack, "旅游"),
		strings.Contains(haystack, "景区"),
		strings.Contains(haystack, "路线"),
		strings.Contains(haystack, "自驾"):
		return ContentVerticalTravelPhotography
	default:
		return ContentVerticalGeneral
	}
}

func ResolveSupplySource(payload map[string]any) string {
	creatorDisclosure, _ := payload["creatorDisclosure"].(map[string]any)
	authorID := strings.TrimSpace(projectionString(payload["authorId"]))
	creatorProfileID := strings.TrimSpace(projectionString(payload["creatorProfileId"]))
	switch {
	case strings.TrimSpace(projectionString(payload["sourceTaskId"])) != "":
		return SupplySourceDataEngineering
	case strings.TrimSpace(projectionString(payload["experienceClaimMode"])) == "editorial_synthesis":
		return SupplySourceDataEngineering
	case creatorDisclosure["type"] == "platform_virtual_creator":
		return SupplySourceDataEngineering
	case strings.HasPrefix(authorID, "agent_author_"), strings.HasPrefix(authorID, "builtin_"):
		return SupplySourceDataEngineering
	case strings.HasPrefix(creatorProfileID, "agent_creator_"), strings.HasPrefix(creatorProfileID, "qwq_creator_"):
		return SupplySourceDataEngineering
	default:
		return SupplySourceUGC
	}
}

func projectedQualityScore(payload map[string]any, semanticCoverage, mediaCompleteness float64) float64 {
	base, ok := numericMapValue(payload["authorQualitySignals"], "qualityScore")
	if !ok {
		base = 0.45
	}
	statusCompleteness := 0.0
	if strings.TrimSpace(projectionString(payload["status"])) == "published" &&
		normalizeVisibility(strings.TrimSpace(projectionString(payload["visibility"]))) == "public" {
		statusCompleteness = 1
	}
	score := 0.55*clampProjected01(base) +
		0.20*mediaCompleteness +
		0.15*semanticCoverage +
		0.10*statusCompleteness
	return clampProjected(score, 0.20, 1)
}

func semanticMentionCoverage(payload map[string]any) float64 {
	if collectionLen(payload["semanticMentions"]) > 0 {
		return 1
	}
	if len(anySlice(payload, "entityRefs")) > 0 && len(anySlice(payload, "tagRefs")) > 0 {
		return 0.7
	}
	if len(anySlice(payload, "entityRefs")) > 0 || len(anySlice(payload, "tagRefs")) > 0 {
		return 0.5
	}
	return 0
}

func mediaCompleteness(payload map[string]any) float64 {
	for _, key := range []string{"coverUrl", "thumbnailUrl", "videoUrl"} {
		if strings.TrimSpace(projectionString(payload[key])) != "" {
			return 1
		}
	}
	for _, key := range []string{"mediaItems", "mediaUrls", "imageUrls", "assets"} {
		if collectionLen(payload[key]) > 0 {
			return 1
		}
	}
	return 0
}

func projectionTokens(payload map[string]any) []string {
	tokens := []string{
		projectionString(payload["contentType"]),
		projectionString(payload["sourceTaskId"]),
	}
	tokens = append(tokens, anySlice(payload, "tagRefs")...)
	tokens = append(tokens, anySlice(payload, "tags")...)
	tokens = append(tokens, anySlice(payload, "entityRefs")...)
	return tokens
}

func projectionString(raw any) string {
	if raw == nil {
		return ""
	}
	return fmt.Sprint(raw)
}

func numericMapValue(raw any, key string) (float64, bool) {
	m, ok := raw.(map[string]any)
	if !ok {
		return 0, false
	}
	return numericValue(m[key])
}

func numericValue(raw any) (float64, bool) {
	switch v := raw.(type) {
	case int:
		return float64(v), true
	case int32:
		return float64(v), true
	case int64:
		return float64(v), true
	case float32:
		return float64(v), true
	case float64:
		return v, true
	default:
		return 0, false
	}
}

func collectionLen(raw any) int {
	switch v := raw.(type) {
	case []any:
		return len(v)
	case []string:
		return len(v)
	case []bson.M:
		return len(v)
	case []map[string]any:
		return len(v)
	default:
		rv := reflect.ValueOf(raw)
		if rv.IsValid() && (rv.Kind() == reflect.Slice || rv.Kind() == reflect.Array) {
			return rv.Len()
		}
		return 0
	}
}

func firstIntersectionHintTarget(raw any) string {
	switch hints := raw.(type) {
	case []any:
		for _, hint := range hints {
			if target := firstIntersectionHintTarget(hint); target != "" {
				return target
			}
		}
	case []map[string]any:
		for _, hint := range hints {
			if target := strings.TrimSpace(projectionString(hint["actionTargetId"])); target != "" {
				return target
			}
		}
	case map[string]any:
		return strings.TrimSpace(projectionString(hints["actionTargetId"]))
	default:
		rv := reflect.ValueOf(raw)
		if !rv.IsValid() {
			return ""
		}
		if rv.Kind() == reflect.Pointer {
			if rv.IsNil() {
				return ""
			}
			rv = rv.Elem()
		}
		switch rv.Kind() {
		case reflect.Slice, reflect.Array:
			for i := 0; i < rv.Len(); i++ {
				if target := firstIntersectionHintTarget(rv.Index(i).Interface()); target != "" {
					return target
				}
			}
		case reflect.Struct:
			field := rv.FieldByName("ActionTargetID")
			if field.IsValid() && field.Kind() == reflect.String {
				return strings.TrimSpace(field.String())
			}
		}
	}
	return ""
}

func normalizeProjectedVertical(raw string) string {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "travel", "travel_photography", "旅行", "旅游":
		return ContentVerticalTravelPhotography
	case "", "<nil>":
		return ContentVerticalGeneral
	default:
		return strings.TrimSpace(strings.ToLower(raw))
	}
}

func clampProjected01(v float64) float64 {
	return clampProjected(v, 0, 1)
}

func clampProjected(v, min, max float64) float64 {
	if math.IsNaN(v) {
		return min
	}
	if v < min {
		return min
	}
	if v > max {
		return max
	}
	return v
}
