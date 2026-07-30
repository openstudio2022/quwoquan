package runtimemedia

import (
	"crypto/sha256"
	"fmt"
	"mime"
	"net/url"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"unicode"
)

// AssetKind identifies the logical media asset type exposed to services/apps.
type AssetKind string

const (
	AssetKindAvatarUser  AssetKind = "avatar_user"
	AssetKindAvatarGroup AssetKind = "avatar_group"
)

var (
	canonicalSliceSegment     = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)
	publicSliceVersionSegment = regexp.MustCompile(`^v([1-9][0-9]*)$`)
)

// DeliveryReference is the only public-safe media projection. Object storage
// keys are deliberately absent: consumers receive a stable slice key and the
// delivery URI built from the injected media endpoint.
type DeliveryReference struct {
	AssetID        string    `json:"assetId"`
	AssetKind      AssetKind `json:"assetKind"`
	Version        int64     `json:"version"`
	PublicSliceKey string    `json:"publicSliceKey"`
	DeliveryURI    string    `json:"deliveryUri"`
}

// NormalizeMediaCDNBase accepts only a complete HTTPS delivery endpoint and
// returns it without a trailing slash. Environment selection belongs to
// composition/configuration; this helper never supplies a fallback endpoint.
func NormalizeMediaCDNBase(raw string) string {
	value := strings.TrimSpace(raw)
	parsed, err := url.Parse(value)
	if err != nil ||
		parsed.Scheme != "https" ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" {
		return ""
	}
	basePath := strings.Trim(parsed.Path, "/")
	if basePath != "" {
		for _, segment := range strings.Split(basePath, "/") {
			if !canonicalSliceSegment.MatchString(segment) {
				return ""
			}
		}
	}
	return strings.TrimRight(parsed.String(), "/")
}

// BuildPublicMediaURL builds the query-free delivery URI for one immutable,
// path-versioned public slice. The path version is the only cache identity;
// redundant version queries and mismatched versions are rejected.
func BuildPublicMediaURL(cdnBaseURL, publicSliceKey string, version int64) string {
	base := NormalizeMediaCDNBase(cdnBaseURL)
	key := normalizePublicSliceKey(publicSliceKey)
	pathVersion, versioned := publicSliceVersion(key)
	if base == "" || key == "" || !versioned || version <= 0 ||
		version != pathVersion {
		return ""
	}
	parsedBase, _ := url.Parse(base)
	basePath := strings.Trim(parsedBase.Path, "/")
	relativeKey := key
	if basePath != "" {
		if !strings.HasPrefix(key, basePath+"/") {
			return ""
		}
		relativeKey = strings.TrimPrefix(key, basePath+"/")
	}
	return fmt.Sprintf("%s/%s", base, relativeKey)
}

// BuildAvatarPublicSliceKey derives the stable public path for a generated
// group-avatar leaf. The storage adapter is responsible for mapping this
// public slice to any CAS object key it uses internally.
func BuildAvatarPublicSliceKey(ownerType, ownerID string, version int64, sourceHash string) string {
	if version <= 0 {
		return ""
	}
	cleanOwnerType := cleanSliceIdentity(ownerType, "unknown")
	cleanOwnerID := cleanSliceIdentity(ownerID, "unknown")
	cleanHash := cleanSliceIdentity(sourceHash, "default")
	if len(cleanHash) > 16 {
		cleanHash = cleanHash[:16]
	}
	return fmt.Sprintf(
		"media/avatar/s/%s/%s/v%d/%s.png",
		cleanOwnerType,
		cleanOwnerID,
		version,
		cleanHash,
	)
}

// BuildContentMediaPublicSliceKey derives the stable public delivery identity
// for a completed MediaAsset. The storage adapter is responsible for
// materializing this public slice from its private CAS object; callers must
// never expose that CAS key to an App or persist it in a Post.
func BuildContentMediaPublicSliceKey(
	mediaType string,
	assetID string,
	version int64,
	contentType string,
) string {
	root := contentMediaPublicRoot(mediaType)
	cleanAssetID := cleanContentAssetIdentity(assetID)
	if root == "" || cleanAssetID == "" || version <= 0 {
		return ""
	}
	return fmt.Sprintf(
		"media/%s/s/asset/%s/v%d/source%s",
		root,
		cleanAssetID,
		version,
		contentMediaPublicExtension(contentType),
	)
}

func contentMediaPublicRoot(mediaType string) string {
	switch strings.ToLower(strings.TrimSpace(mediaType)) {
	case "avatar":
		return "avatar"
	case "image":
		return "image"
	case "video":
		return "video"
	case "audio", "file":
		return "attachment"
	default:
		return ""
	}
}

func cleanContentAssetIdentity(raw string) string {
	value := strings.TrimSpace(raw)
	if value == "" || strings.ContainsAny(value, `/\`) {
		return ""
	}
	for _, character := range value {
		if unicode.IsSpace(character) || unicode.IsControl(character) {
			return ""
		}
	}
	if canonicalSliceSegment.MatchString(value) {
		return value
	}
	sum := sha256.Sum256([]byte(value))
	return fmt.Sprintf("unicode-%x", sum[:16])
}

func contentMediaPublicExtension(contentType string) string {
	normalized := strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0]))
	switch normalized {
	case "image/jpeg":
		return ".jpg"
	case "image/png":
		return ".png"
	case "image/webp":
		return ".webp"
	case "image/gif":
		return ".gif"
	case "video/mp4":
		return ".mp4"
	case "video/webm":
		return ".webm"
	case "audio/mpeg":
		return ".mp3"
	case "audio/mp4":
		return ".m4a"
	}
	if extensions, _ := mime.ExtensionsByType(normalized); len(extensions) > 0 {
		if extension := filepath.Ext(extensions[0]); extension != "" {
			return strings.ToLower(extension)
		}
	}
	return ".bin"
}

func BuildAvatarGroupDeliveryReference(
	conversationID string,
	assetID string,
	version int64,
	sourceHash string,
	cdnBaseURL string,
) DeliveryReference {
	publicSliceKey := BuildAvatarPublicSliceKey(
		"conversation",
		conversationID,
		version,
		sourceHash,
	)
	return DeliveryReference{
		AssetID:        strings.TrimSpace(assetID),
		AssetKind:      AssetKindAvatarGroup,
		Version:        version,
		PublicSliceKey: publicSliceKey,
		DeliveryURI:    BuildPublicMediaURL(cdnBaseURL, publicSliceKey, version),
	}
}

func cleanSliceIdentity(raw string, fallback string) string {
	value := strings.TrimSpace(raw)
	if value == "" {
		return fallback
	}
	value = strings.ReplaceAll(value, "/", "-")
	value = strings.ReplaceAll(value, "\\", "-")
	if !canonicalSliceSegment.MatchString(value) {
		return fallback
	}
	return value
}

func normalizePublicSliceKey(raw string) string {
	value := strings.Trim(strings.TrimSpace(raw), "/")
	if value == "" || strings.Contains(value, "://") || strings.ContainsAny(value, "?#\\") {
		return ""
	}
	segments := strings.Split(value, "/")
	if len(segments) < 4 || segments[0] != "media" || segments[2] != "s" {
		return ""
	}
	for _, segment := range segments {
		if !canonicalSliceSegment.MatchString(segment) || segment == "." || segment == ".." {
			return ""
		}
	}
	return value
}

func publicSliceVersion(publicSliceKey string) (int64, bool) {
	version := int64(0)
	found := false
	for _, segment := range strings.Split(publicSliceKey, "/") {
		match := publicSliceVersionSegment.FindStringSubmatch(segment)
		if match == nil {
			continue
		}
		if found {
			return 0, false
		}
		parsed, err := strconv.ParseInt(match[1], 10, 64)
		if err != nil || parsed <= 0 {
			return 0, false
		}
		version = parsed
		found = true
	}
	return version, found
}

// PublicSliceVersion returns the single positive version encoded in a
// canonical public-slice path. Callers that only receive a slice key must use
// this value when invoking BuildPublicMediaURL; zero is never an unspecified
// or compatibility version.
func PublicSliceVersion(publicSliceKey string) (int64, bool) {
	key := normalizePublicSliceKey(publicSliceKey)
	if key == "" {
		return 0, false
	}
	return publicSliceVersion(key)
}
