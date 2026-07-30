package runtimemedia

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
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
		if err := validateReleaseMediaAssetClosure(releaseRoot, asset); err != nil {
			return nil, fmt.Errorf(
				"release MediaAsset %q provenance closure is invalid: %w",
				asset.AssetID,
				err,
			)
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
		PublicURL:         BuildPublicMediaURL(base, asset.PublicSliceKey, asset.Version),
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
	// Base validation must be identical to BuildPublicMediaURL. A weaker
	// pre-check can otherwise report a successful resolution with an empty URL.
	return NormalizeMediaCDNBase(raw)
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

func validateReleaseMediaAssetClosure(
	releaseRoot string,
	asset ReleaseMediaAsset,
) error {
	owners := make(map[string]struct{}, len(asset.OwnerRefs))
	for _, raw := range asset.OwnerRefs {
		owner := strings.TrimSpace(raw)
		if !canonicalReleaseMediaOwnerRef(owner) {
			return fmt.Errorf("ownerRefs contains non-canonical ref %q", raw)
		}
		if _, exists := owners[owner]; exists {
			return fmt.Errorf("ownerRefs contains duplicate ref %q", owner)
		}
		owners[owner] = struct{}{}
	}

	rightsByOwner := make(map[string]int, len(owners))
	seenRights := make(map[string]struct{}, len(asset.RightsSnapshotRefs))
	for _, raw := range asset.RightsSnapshotRefs {
		ref := strings.TrimSpace(raw)
		if !canonicalReleaseRightsRef(ref) {
			return fmt.Errorf("rightsSnapshotRefs contains non-canonical ref %q", raw)
		}
		if _, exists := seenRights[ref]; exists {
			return fmt.Errorf("rightsSnapshotRefs contains duplicate ref %q", ref)
		}
		seenRights[ref] = struct{}{}

		owner := releaseRightsOwner(ref)
		if _, exists := owners[owner]; !exists {
			return fmt.Errorf(
				"rightsSnapshotRefs entry %q has no matching ownerRefs entry",
				ref,
			)
		}
		if err := validateReleaseRightsBinding(
			releaseRoot,
			ref,
			asset.AssetID,
			asset.SHA256,
		); err != nil {
			return err
		}
		rightsByOwner[owner]++
	}
	for owner := range owners {
		if rightsByOwner[owner] == 0 {
			return fmt.Errorf(
				"ownerRefs entry %q has no bound rightsSnapshotRefs entry",
				owner,
			)
		}
	}
	return nil
}

func canonicalReleaseMediaOwnerRef(ref string) bool {
	if ref == "" ||
		strings.Contains(ref, `\`) ||
		path.IsAbs(ref) ||
		path.Clean(ref) != ref {
		return false
	}
	parts := strings.Split(ref, "/")
	if len(parts) < 2 {
		return false
	}
	switch parts[0] {
	case "creators", "entities", "posts":
	default:
		return false
	}
	for _, part := range parts[1:] {
		if strings.TrimSpace(part) == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}

func canonicalReleaseRightsRef(ref string) bool {
	if ref == "" ||
		strings.Contains(ref, `\`) ||
		path.IsAbs(ref) ||
		path.Clean(ref) != ref ||
		!strings.HasPrefix(ref, "objects/") {
		return false
	}
	owner := releaseRightsOwner(ref)
	if !canonicalReleaseMediaOwnerRef(owner) {
		return false
	}
	suffix := strings.TrimPrefix(
		ref,
		"objects/"+owner+"/rights_snapshots/",
	)
	return suffix != "" &&
		!strings.Contains(suffix, "/") &&
		suffix != "." &&
		suffix != ".." &&
		strings.HasSuffix(suffix, ".json")
}

func releaseRightsOwner(ref string) string {
	const marker = "/rights_snapshots/"
	if !strings.HasPrefix(ref, "objects/") {
		return ""
	}
	value := strings.TrimPrefix(ref, "objects/")
	index := strings.Index(value, marker)
	if index <= 0 {
		return ""
	}
	return value[:index]
}

func validateReleaseRightsBinding(
	releaseRoot string,
	ref string,
	expectedAssetID string,
	expectedSHA256 string,
) error {
	filePath := filepath.Join(
		releaseRoot,
		"payload",
		filepath.FromSlash(ref),
	)
	raw, err := os.ReadFile(filePath)
	if err != nil {
		return fmt.Errorf("read rights snapshot %q: %w", ref, err)
	}
	var document struct {
		AssetID       string `json:"assetId"`
		ManifestAsset struct {
			AssetID string `json:"assetId"`
			SHA256  string `json:"sha256"`
		} `json:"manifestAsset"`
	}
	if err := json.Unmarshal(raw, &document); err != nil {
		return fmt.Errorf("decode rights snapshot %q: %w", ref, err)
	}
	if strings.TrimSpace(document.AssetID) != expectedAssetID ||
		strings.TrimSpace(document.ManifestAsset.AssetID) != expectedAssetID ||
		strings.TrimSpace(document.ManifestAsset.SHA256) != expectedSHA256 {
		return fmt.Errorf(
			"rights snapshot %q does not bind MediaAsset identity",
			ref,
		)
	}
	return nil
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
