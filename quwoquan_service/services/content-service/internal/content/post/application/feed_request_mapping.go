package post

import (
	"strings"
)

func mapContentTypeToViewType(contentType string) string {
	switch strings.TrimSpace(contentType) {
	case "micro":
		return "moment"
	case "image":
		return "image"
	case "video":
		return "video"
	case "article":
		return "article"
	default:
		return "image"
	}
}

func normalizeRequestType(t string) string {
	switch strings.TrimSpace(strings.ToLower(t)) {
	case "", "recommended", "following", "travel", "travel_photography", "premium", "similar", "featured", "immersive", "精品", "旅行", "旅游":
		return ""
	case "photo":
		return "image"
	case "note":
		return "article"
	default:
		return strings.TrimSpace(strings.ToLower(t))
	}
}

func normalizeRequestedIdentity(identity string) string {
	switch strings.TrimSpace(strings.ToLower(identity)) {
	case "moment", "work":
		return strings.TrimSpace(strings.ToLower(identity))
	default:
		return ""
	}
}
