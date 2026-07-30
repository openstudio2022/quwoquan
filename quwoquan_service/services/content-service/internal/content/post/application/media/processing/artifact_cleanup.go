package mediaprocessing

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

// ImageArtifactSource is the cleanup-relevant part of one historical image
// descriptor. Persistence adapters map their own document shape into this
// application contract instead of importing a sibling infrastructure package.
type ImageArtifactSource struct {
	NormalizedObjectKey string
	PublicSliceKey      string
}

// ArtifactCleanupSource is the complete, storage-neutral MediaAsset artifact
// snapshot needed to create one idempotent cleanup unit.
type ArtifactCleanupSource struct {
	AssetID                      string
	ObjectKey                    string
	ImageNormalizedObjectKey     string
	ImagePublicSliceKey          string
	VideoPublicSliceKey          string
	CoverPublicSliceKey          string
	PreviewTrackManifestSliceKey string
	HistoricalImageArtifacts     []ImageArtifactSource
}

// PlanArtifactCleanup derives all exact keys and asset-bounded prefixes for a
// retryable cleanup. Its work identity is stable by (event, asset).
func PlanArtifactCleanup(
	eventID string,
	source ArtifactCleanupSource,
) ArtifactCleanupWork {
	publicSliceKeys := []string{
		source.ImagePublicSliceKey,
		source.VideoPublicSliceKey,
		source.CoverPublicSliceKey,
		source.PreviewTrackManifestSliceKey,
	}
	privateObjectKeys := []string{
		source.ObjectKey,
		source.ImageNormalizedObjectKey,
	}
	for _, artifact := range source.HistoricalImageArtifacts {
		publicSliceKeys = append(publicSliceKeys, artifact.PublicSliceKey)
		privateObjectKeys = append(
			privateObjectKeys,
			artifact.NormalizedObjectKey,
		)
	}
	publicSliceKeys = uniqueArtifactStrings(publicSliceKeys)
	privateObjectKeys = uniqueArtifactStrings(privateObjectKeys)
	publicPrefixes := make([]string, 0, len(publicSliceKeys))
	privatePrefixes := make([]string, 0, len(privateObjectKeys))
	for _, key := range publicSliceKeys {
		if prefix := publicAssetPrefix(key); prefix != "" {
			publicPrefixes = append(publicPrefixes, prefix)
		}
	}
	for _, key := range privateObjectKeys {
		if prefix := privateAssetPrefix(key); prefix != "" {
			privatePrefixes = append(privatePrefixes, prefix)
		}
	}
	return ArtifactCleanupWork{
		WorkID:            artifactCleanupWorkID(eventID, source.AssetID),
		PublicSliceKeys:   publicSliceKeys,
		PublicPrefixes:    uniqueArtifactStrings(publicPrefixes),
		PrivateObjectKeys: privateObjectKeys,
		PrivatePrefixes:   uniqueArtifactStrings(privatePrefixes),
	}
}

func publicAssetPrefix(key string) string {
	key = strings.Trim(strings.TrimSpace(key), "/")
	const marker = "/s/asset/"
	index := strings.Index(key, marker)
	if index < 0 {
		return ""
	}
	assetStart := index + len(marker)
	assetEnd := strings.Index(key[assetStart:], "/")
	if assetEnd <= 0 {
		return ""
	}
	assetID := key[assetStart : assetStart+assetEnd]
	if assetID == "" || strings.ContainsAny(assetID, "\\?#") ||
		strings.Contains(assetID, "..") {
		return ""
	}
	return key[:assetStart+assetEnd+1]
}

func privateAssetPrefix(key string) string {
	key = strings.Trim(strings.TrimSpace(key), "/")
	for _, root := range []string{
		"media/processed/image/",
		"media/processed/video/",
	} {
		if !strings.HasPrefix(key, root) {
			continue
		}
		remainder := strings.TrimPrefix(key, root)
		segmentEnd := strings.Index(remainder, "/")
		if segmentEnd <= 0 {
			return ""
		}
		assetID := remainder[:segmentEnd]
		if strings.ContainsAny(assetID, "\\?#") ||
			strings.Contains(assetID, "..") {
			return ""
		}
		return root + assetID + "/"
	}
	return ""
}

func artifactCleanupWorkID(eventID string, assetID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(eventID) + "\x00" + strings.TrimSpace(assetID),
	))
	return hex.EncodeToString(sum[:])
}

func uniqueArtifactStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}
