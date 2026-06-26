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

func findWritableFields(routes []routeDef, operation string) []string {
	for _, r := range routes {
		if strings.EqualFold(r.Operation, operation) {
			return r.WritableFields
		}
	}
	return nil
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
