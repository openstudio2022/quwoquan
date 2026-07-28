package runtimemedia

import (
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

const (
	releaseMediaManifestSchema = "quwoquan_data.release_media_manifest"
	releaseMediaSourceOwner    = "qwq_data"
)

var releaseMediaSHA256Pattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

// ReleaseMediaAsset is the immutable Data release authority consumed by
// service importers. Private CAS/object-storage fields are intentionally absent.
type ReleaseMediaAsset struct {
	AssetID            string   `json:"assetId"`
	Kind               string   `json:"kind"`
	Version            int64    `json:"version"`
	ContentType        string   `json:"contentType"`
	PublicSliceKey     string   `json:"publicSliceKey"`
	SHA256             string   `json:"sha256"`
	Bytes              int64    `json:"bytes"`
	OwnerRefs          []string `json:"ownerRefs"`
	RightsSnapshotRefs []string `json:"rightsSnapshotRefs"`
}

type releaseMediaManifest struct {
	Schema      string              `json:"schema"`
	ReleaseID   string              `json:"releaseId"`
	SourceOwner string              `json:"sourceOwner"`
	Assets      []ReleaseMediaAsset `json:"assets"`
	Issues      []string            `json:"issues"`
	Counts      struct {
		Assets int `json:"assets"`
		Issues int `json:"issues"`
	} `json:"counts"`
}

// MediaDeliveryBases selects the public endpoint by canonical MediaAsset kind.
// Each importer must inject only environment topology values; no fallback is
// supplied when a required kind endpoint is absent.
type MediaDeliveryBases struct {
	Avatar string
	Image  string
	Video  string
}

// ResolvedReleaseMediaAsset contains the public-safe projection of one
// release-authorized media binding.
type ResolvedReleaseMediaAsset struct {
	ReleaseMediaAsset
	PublicURL string
}

// LoadReleaseMediaAssets decodes and validates one immutable release authority.
func LoadReleaseMediaAssets(
	releaseRoot string,
	expectedReleaseID string,
) (map[string]ReleaseMediaAsset, error) {
	path := filepath.Join(releaseRoot, "payload", "media_manifest.json")
	file, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("read release media manifest: %w", err)
	}
	defer file.Close()

	decoder := json.NewDecoder(file)
	decoder.DisallowUnknownFields()
	var manifest releaseMediaManifest
	if err := decoder.Decode(&manifest); err != nil {
		return nil, fmt.Errorf("decode release media manifest: %w", err)
	}
	expectedReleaseID = strings.TrimSpace(expectedReleaseID)
	if manifest.Schema != releaseMediaManifestSchema ||
		expectedReleaseID == "" ||
		manifest.ReleaseID != expectedReleaseID ||
		manifest.SourceOwner != releaseMediaSourceOwner ||
		len(manifest.Issues) != 0 ||
		manifest.Counts.Issues != 0 ||
		manifest.Counts.Assets != len(manifest.Assets) {
		return nil, fmt.Errorf("release media manifest contract is invalid")
	}

	result := make(map[string]ReleaseMediaAsset, len(manifest.Assets))
	sliceOwners := make(map[string]string, len(manifest.Assets))
	for _, asset := range manifest.Assets {
		asset.AssetID = strings.TrimSpace(asset.AssetID)
		asset.Kind = strings.ToLower(strings.TrimSpace(asset.Kind))
		asset.ContentType = strings.ToLower(strings.TrimSpace(asset.ContentType))
		asset.PublicSliceKey = strings.TrimSpace(asset.PublicSliceKey)
		asset.SHA256 = strings.TrimSpace(asset.SHA256)
		expectedSlice := BuildContentMediaPublicSliceKey(
			asset.Kind,
			asset.AssetID,
			asset.Version,
			asset.ContentType,
		)
		if asset.AssetID == "" ||
			asset.Version <= 0 ||
			asset.Bytes <= 0 ||
			!releaseMediaSHA256Pattern.MatchString(asset.SHA256) ||
			!releaseKindMatchesContentType(asset.Kind, asset.ContentType) ||
			expectedSlice == "" ||
			asset.PublicSliceKey != expectedSlice ||
			!nonEmptyReleaseRefs(asset.OwnerRefs) ||
			!nonEmptyReleaseRefs(asset.RightsSnapshotRefs) {
			return nil, fmt.Errorf("release MediaAsset %q is invalid", asset.AssetID)
		}
		if _, exists := result[asset.AssetID]; exists {
			return nil, fmt.Errorf("release MediaAsset identity is duplicated: %s", asset.AssetID)
		}
		if owner, exists := sliceOwners[asset.PublicSliceKey]; exists {
			return nil, fmt.Errorf(
				"release public media slice is shared by %s and %s",
				owner,
				asset.AssetID,
			)
		}
		result[asset.AssetID] = asset
		sliceOwners[asset.PublicSliceKey] = asset.AssetID
	}
	return result, nil
}

// ResolveReleaseMediaAsset validates an object-level binding against the
// release authority and returns its kind-specific public delivery URL.
func ResolveReleaseMediaAsset(
	assets map[string]ReleaseMediaAsset,
	bases MediaDeliveryBases,
	assetID string,
	expectedKind string,
	expectedSHA256 string,
	expectedOwnerRef string,
) (ResolvedReleaseMediaAsset, error) {
	assetID = strings.TrimSpace(assetID)
	expectedKind = strings.ToLower(strings.TrimSpace(expectedKind))
	expectedSHA256 = strings.TrimSpace(expectedSHA256)
	expectedOwnerRef = strings.TrimSpace(expectedOwnerRef)
	asset, exists := assets[assetID]
	if !exists {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"MediaAsset %q is absent from release media authority",
			assetID,
		)
	}
	if expectedKind == "" || asset.Kind != expectedKind {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"MediaAsset %q kind differs from object binding",
			assetID,
		)
	}
	if expectedSHA256 == "" || asset.SHA256 != expectedSHA256 {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"MediaAsset %q sha256 differs from object binding",
			assetID,
		)
	}
	if expectedOwnerRef == "" || !containsReleaseRef(asset.OwnerRefs, expectedOwnerRef) {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"MediaAsset %q ownerRefs do not authorize object %q",
			assetID,
			expectedOwnerRef,
		)
	}
	if !rightsAuthorizeReleaseOwner(asset.RightsSnapshotRefs, expectedOwnerRef) {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"MediaAsset %q rightsSnapshotRefs do not bind object %q",
			assetID,
			expectedOwnerRef,
		)
	}
	base := bases.forKind(asset.Kind)
	if base == "" {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"public media base URL is unavailable for kind %q",
			asset.Kind,
		)
	}
	return ResolvedReleaseMediaAsset{
		ReleaseMediaAsset: asset,
		PublicURL:         BuildPublicMediaURL(base, asset.PublicSliceKey, 0),
	}, nil
}

func (bases MediaDeliveryBases) forKind(kind string) string {
	var raw string
	switch kind {
	case "avatar":
		raw = bases.Avatar
	case "image":
		raw = bases.Image
	case "video":
		raw = bases.Video
	default:
		return ""
	}
	value := strings.TrimRight(strings.TrimSpace(raw), "/")
	parsed, err := url.Parse(value)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" {
		return ""
	}
	return value
}

func releaseKindMatchesContentType(kind string, contentType string) bool {
	switch kind {
	case "avatar", "image":
		return strings.HasPrefix(contentType, "image/")
	case "video":
		return strings.HasPrefix(contentType, "video/")
	default:
		return false
	}
}

func nonEmptyReleaseRefs(refs []string) bool {
	if len(refs) == 0 {
		return false
	}
	for _, ref := range refs {
		if strings.TrimSpace(ref) == "" {
			return false
		}
	}
	return true
}

func containsReleaseRef(refs []string, expected string) bool {
	for _, ref := range refs {
		if strings.TrimSpace(ref) == expected {
			return true
		}
	}
	return false
}

func rightsAuthorizeReleaseOwner(refs []string, ownerRef string) bool {
	prefix := "objects/" + strings.Trim(ownerRef, "/") + "/rights_snapshots/"
	for _, ref := range refs {
		if strings.HasPrefix(strings.TrimSpace(ref), prefix) {
			return true
		}
	}
	return false
}
