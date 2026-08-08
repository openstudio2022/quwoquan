package main

import (
	"fmt"
	"strconv"
	"strings"
)

func buildPostDefaults(fields []fieldDef) map[string]string {
	defaults := map[string]string{}
	for _, f := range fields {
		if v, ok := parseDefaultValue(f.Constraints); ok {
			defaults[f.Name] = v
			continue
		}
		if strings.HasPrefix(f.Type, "[]") {
			defaults[f.Name] = dartEmptyListExpr(f.Type)
		}
	}
	return defaults
}

// buildPostSnapshotFieldByteLimits derives the per-field canonical UTF-8 byte
// admission table for the App-consumed projection of one aggregate. The exposed
// wire keys come from the projection's canonical client field set; the limit
// value comes from canonical `max_utf8_bytes`, declared either on the projection
// field itself or on the aggregate field it projects. Declaring both for the
// same wire key with different values would make one key carry two truth
// sources, so that combination fails closed instead of silently picking one.
func buildPostSnapshotFieldByteLimits(
	fields []fieldDef,
	projection *projectionFile,
) (map[string]int, error) {
	limitsByCanonicalName := map[string]int{}
	for _, field := range fields {
		if field.MaxUTF8Bytes <= 0 {
			continue
		}
		limitsByCanonicalName[field.Name] = field.MaxUTF8Bytes
		if field.Source != "" {
			limitsByCanonicalName[field.Source] = field.MaxUTF8Bytes
		}
	}
	limits := map[string]int{}
	for _, field := range projection.canonicalClientFields() {
		canonicalName := field.Source
		if canonicalName == "" {
			canonicalName = field.Name
		}
		aggregateLimit := limitsByCanonicalName[canonicalName]
		projectionLimit := field.MaxUTF8Bytes
		if aggregateLimit > 0 && projectionLimit > 0 &&
			aggregateLimit != projectionLimit {
			return nil, fmt.Errorf(
				"projection field %s declares max_utf8_bytes %d while canonical field %s declares %d",
				field.Name,
				projectionLimit,
				canonicalName,
				aggregateLimit,
			)
		}
		if projectionLimit > 0 {
			limits[field.Name] = projectionLimit
			continue
		}
		if aggregateLimit > 0 {
			limits[field.Name] = aggregateLimit
		}
	}
	return limits, nil
}

func dartEmptyListExpr(t string) string {
	switch t {
	case "[]float32", "[]float64":
		return "<double>[]"
	case "[]int":
		return "<int>[]"
	case "[]bool":
		return "<bool>[]"
	case "[]object":
		return "<Map<String, dynamic>>[]"
	default:
		return "<String>[]"
	}
}

func parseDefaultValue(constraints []string) (string, bool) {
	for _, c := range constraints {
		if !strings.HasPrefix(c, "DEFAULT_") {
			continue
		}
		raw := strings.TrimPrefix(c, "DEFAULT_")
		if raw == "FALSE" {
			return "false", true
		}
		if raw == "TRUE" {
			return "true", true
		}
		if n, err := strconv.Atoi(raw); err == nil {
			return strconv.Itoa(n), true
		}
		return fmt.Sprintf("'%s'", strings.ToLower(raw)), true
	}
	return "", false
}

func buildFeedDefaults(postDefaults map[string]string) map[string]string {
	get := func(key, fallback string) string {
		if v, ok := postDefaults[key]; ok && v != "" {
			return v
		}
		return fallback
	}
	// NOTE: These defaults are current Map<String,dynamic> compatibility constants.
	// New code should use FeedItemDto (feed_item_dto.g.dart) instead.
	return map[string]string{
		"coverUrl":         get("coverUrl", "''"),
		"isLocalGenerated": "true",
		"tagRefs":          get("tagRefs", "<String>[]"),
		"thumbnailUrl":     get("coverUrl", "''"),
		"videoUrl":         get("videoUrl", "''"),
		"visibility":       get("visibility", "'public'"),
	}
}

func buildContentTypeToRender(contentTypes []string) map[string]string {
	// renderType 与 ContentType 真相源 (types.yaml) canonical 一致；不再把 micro 映射成 moment。
	out := map[string]string{}
	for _, ct := range contentTypes {
		out[ct] = ct
	}
	return out
}

func buildDiscoveryMappings(contentTypes []string) (map[string]string, map[string]string) {
	// requestType 全部使用 canonical ContentType（micro/image/...），无 moment/photo 同义词。
	feedCategoryToType := map[string]string{
		"recommended": "micro",
		"following":   "micro",
	}
	for _, ct := range contentTypes {
		category := ct
		feedType := ct
		if ct == "image" {
			category = "images"
		}
		feedCategoryToType[category] = feedType
	}

	appTabToCategory := map[string]string{
		"micro":   "recommended",
		"image":   "images",
		"video":   "video",
		"article": "article",
	}
	return feedCategoryToType, appTabToCategory
}

func buildMutationRoutes(routes []routeDef, operations []string) map[string]string {
	out := map[string]string{}
	for _, op := range operations {
		r := findRoute(routes, op)
		if r.Path != "" {
			out[op] = r.Path
		}
	}
	return out
}

func findRoute(routes []routeDef, operation string) routeDef {
	for _, r := range routes {
		if strings.EqualFold(r.Operation, operation) {
			return r
		}
	}
	return routeDef{}
}

func paginationLimitDefault(shared *sharedTypes, fallback int) int {
	pagination, ok := shared.Types["Pagination"]
	if !ok {
		return fallback
	}
	for _, f := range pagination.Fields {
		if f.Name != "limit" || f.Default == nil {
			continue
		}
		switch v := f.Default.(type) {
		case int:
			return v
		case int64:
			return int(v)
		case float64:
			return int(v)
		}
	}
	return fallback
}

func operationDefaultLimit(operation string, pageLimit int) int {
	switch operation {
	case "ListUserCircles":
		return 50
	case "SyncMessages":
		return 500
	default:
		return pageLimit
	}
}

// ── renderers ─────────────────────────────────────────────────────────────────
