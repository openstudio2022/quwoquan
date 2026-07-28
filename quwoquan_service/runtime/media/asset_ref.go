package runtimemedia

import (
	"crypto/sha256"
	"fmt"
	"mime"
	"net/url"
	"path/filepath"
	"regexp"
	"strings"
	"unicode"
)

// AssetKind identifies the logical media asset type exposed to services/apps.
type AssetKind string

const (
	AssetKindAvatarUser  AssetKind = "avatar_user"
	AssetKindAvatarGroup AssetKind = "avatar_group"
)

var canonicalSliceSegment = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._-]*$`)

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

// AssetRef is runtime-media's internal state. It may carry the storage key
// while a write is in progress, but it must never be JSON-serialized across a
// service or UI boundary. Use DeliveryReference for those boundaries.
type AssetRef struct {
	AssetID        string    `json:"-"`
	AssetKind      AssetKind `json:"-"`
	OwnerType      string    `json:"-"`
	OwnerID        string    `json:"-"`
	Version        int64     `json:"-"`
	ObjectKey      string    `json:"-"`
	PublicSliceKey string    `json:"-"`
	DeliveryURI    string    `json:"-"`
}

// DeliveryReference projects the public-safe form of an internal asset.
func (ref AssetRef) DeliveryReference() DeliveryReference {
	return DeliveryReference{
		AssetID:        ref.AssetID,
		AssetKind:      ref.AssetKind,
		Version:        ref.Version,
		PublicSliceKey: ref.PublicSliceKey,
		DeliveryURI:    ref.DeliveryURI,
	}
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
	return strings.TrimRight(parsed.String(), "/")
}

// BuildPublicMediaURL builds a delivery URI from an injected HTTPS endpoint
// and a canonical public slice key. It does not accept CAS/object-storage keys,
// rewrite paths, infer media types, or fall back to another endpoint.
func BuildPublicMediaURL(cdnBaseURL, publicSliceKey string, version int64) string {
	base := NormalizeMediaCDNBase(cdnBaseURL)
	key := normalizePublicSliceKey(publicSliceKey)
	if base == "" || key == "" {
		return ""
	}
	parsedBase, _ := url.Parse(base)
	basePath := strings.Trim(parsedBase.Path, "/")
	relativeKey := key
	if basePath != "" && strings.HasPrefix(key, basePath+"/") {
		relativeKey = strings.TrimPrefix(key, basePath+"/")
	}
	deliveryURI := fmt.Sprintf("%s/%s", base, relativeKey)
	if version > 0 {
		deliveryURI = fmt.Sprintf("%s?v=%d", deliveryURI, version)
	}
	return deliveryURI
}

// BuildAssetURL is retained as a source-compatible wrapper. It intentionally
// does not invent an HTTPS scheme for a bare host; callers must inject a fully
// validated endpoint through configuration.
func BuildAssetURL(cdnBaseURL, publicSliceKey string, version int64) string {
	return BuildPublicMediaURL(cdnBaseURL, publicSliceKey, version)
}

// BuildAvatarPublicSliceKey derives the stable public path for a generated
// group-avatar leaf. The storage adapter is responsible for mapping this
// public slice to any CAS object key it uses internally.
func BuildAvatarPublicSliceKey(ownerType, ownerID string, version int64, sourceHash string) string {
	cleanOwnerType := cleanSliceIdentity(ownerType, "unknown")
	cleanOwnerID := cleanSliceIdentity(ownerID, "unknown")
	cleanHash := cleanSliceIdentity(sourceHash, "default")
	if len(cleanHash) > 16 {
		cleanHash = cleanHash[:16]
	}
	if version <= 0 {
		version = 1
	}
	return fmt.Sprintf(
		"media/avatar/s/%s/%s/v%d/%s.png",
		cleanOwnerType,
		cleanOwnerID,
		version,
		cleanHash,
	)
}

// BuildAvatarObjectKey is kept for storage-adapter compatibility. It returns
// the public slice identity; callers must not expose it as a CAS key.
func BuildAvatarObjectKey(ownerType, ownerID string, version int64, sourceHash string) string {
	return BuildAvatarPublicSliceKey(ownerType, ownerID, version, sourceHash)
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
	if root == "" || cleanAssetID == "" {
		return ""
	}
	if version <= 0 {
		version = 1
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

func BuildAvatarGroupAssetRef(
	conversationID string,
	assetID string,
	version int64,
	sourceHash string,
	cdnBaseURL string,
) AssetRef {
	publicSliceKey := BuildAvatarPublicSliceKey(
		"conversation",
		conversationID,
		version,
		sourceHash,
	)
	return AssetRef{
		AssetID:        strings.TrimSpace(assetID),
		AssetKind:      AssetKindAvatarGroup,
		OwnerType:      "conversation",
		OwnerID:        strings.TrimSpace(conversationID),
		Version:        version,
		ObjectKey:      publicSliceKey,
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
