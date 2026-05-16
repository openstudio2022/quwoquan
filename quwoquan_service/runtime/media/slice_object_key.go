package runtimemedia

import (
	"fmt"
	"regexp"
	"strings"
)

const (
	LegacyAvatarSliceID = "legacy-avatar"
	LegacyImageSliceID  = "legacy-image"
	LegacyVideoSliceID  = "legacy-video"
)

var slicedObjectKeyPattern = regexp.MustCompile(`(?:^|/)s/([^/]+)/`)

// BuildSlicedObjectKey builds the canonical object key that carries sliceId in path.
func BuildSlicedObjectKey(
	domain string,
	assetKind string,
	sliceID string,
	ownerType string,
	ownerID string,
	assetID string,
	variant string,
	ext string,
) string {
	cleanDomain := normalizeObjectKeyPart(domain, "media")
	cleanAssetKind := normalizeObjectKeyPart(assetKind, "asset")
	cleanSliceID := normalizeObjectKeyPart(sliceID, "slice-unknown")
	cleanOwnerType := normalizeObjectKeyPart(ownerType, "owner")
	cleanOwnerID := normalizeObjectKeyPart(ownerID, "unknown")
	cleanAssetID := normalizeObjectKeyPart(assetID, "asset")
	cleanVariant := normalizeObjectKeyPart(variant, "origin")
	cleanExt := normalizeFileExt(ext)
	return fmt.Sprintf(
		"%s/%s/s/%s/%s/%s/%s_%s.%s",
		cleanDomain,
		cleanAssetKind,
		cleanSliceID,
		cleanOwnerType,
		cleanOwnerID,
		cleanAssetID,
		cleanVariant,
		cleanExt,
	)
}

// ExtractSliceIDFromObjectKey returns the explicit sliceId carried in objectKey.
func ExtractSliceIDFromObjectKey(objectKey string) string {
	key := strings.Trim(strings.TrimSpace(objectKey), "/")
	if key == "" {
		return ""
	}
	match := slicedObjectKeyPattern.FindStringSubmatch(key)
	if len(match) != 2 {
		return ""
	}
	return strings.TrimSpace(match[1])
}

// LegacySliceIDFromObjectKey keeps old fixture paths routable before all assets move
// to the explicit /s/{sliceId}/ form.
func LegacySliceIDFromObjectKey(objectKey string) string {
	key := strings.Trim(strings.TrimSpace(objectKey), "/")
	switch {
	case strings.HasPrefix(key, "media/avatar/"), strings.HasPrefix(key, "media/background/"):
		return LegacyAvatarSliceID
	case strings.HasPrefix(key, "media/image/"):
		return LegacyImageSliceID
	case strings.HasPrefix(key, "media/video/"):
		return LegacyVideoSliceID
	default:
		return ""
	}
}

// ResolveSliceIDFromObjectKey prefers explicit sliceId and falls back to legacy prefix routing.
func ResolveSliceIDFromObjectKey(objectKey string) string {
	if sliceID := ExtractSliceIDFromObjectKey(objectKey); sliceID != "" {
		return sliceID
	}
	return LegacySliceIDFromObjectKey(objectKey)
}

func normalizeObjectKeyPart(value string, fallback string) string {
	cleaned := strings.Trim(value, "/ \t\r\n")
	if cleaned == "" {
		return fallback
	}
	cleaned = strings.ReplaceAll(cleaned, " ", "-")
	cleaned = strings.ReplaceAll(cleaned, ":", "-")
	return cleaned
}

func normalizeFileExt(value string) string {
	cleaned := strings.Trim(value, ". \t\r\n")
	if cleaned == "" {
		return "bin"
	}
	return strings.ToLower(cleaned)
}
