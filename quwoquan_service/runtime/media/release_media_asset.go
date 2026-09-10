package runtimemedia

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
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

// ReleaseMediaAsset 保留 immutable Data 媒体身份、公开 slice 和真实来源权利引用。
// 普通原图签名权限不属于 release 交付类别。
type ReleaseMediaAsset struct {
	AssetID            string   `json:"assetId"`
	Kind               string   `json:"kind"`
	Version            int64    `json:"version"`
	ContentType        string   `json:"contentType"`
	PublicSliceKey     string   `json:"publicSliceKey,omitempty"`
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

// ResolvedReleaseMediaAsset 是公开交付投影，DeliveryRef 只保存 canonical public URL。
type ResolvedReleaseMediaAsset struct {
	ReleaseMediaAsset
	PublicURL   string
	DeliveryRef string
}

// LoadReleaseMediaAssets decodes and validates one immutable release authority.
// 所有 release 只接受显式 canonical publicSliceKey（DEC-031）。
func LoadReleaseMediaAssets(
	releaseRoot string,
	expectedReleaseID string,
) (map[string]ReleaseMediaAsset, error) {
	file, err := openReleaseMediaFile(releaseRoot, "media_manifest.json")
	if err != nil {
		return nil, fmt.Errorf("read release media manifest: %w", err)
	}
	defer file.Close()

	var manifest releaseMediaManifest
	if err := decodeReleaseMediaDocument(file, &manifest, true); err != nil {
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
		if asset.AssetID == "" ||
			asset.Version <= 0 ||
			asset.Bytes <= 0 ||
			!releaseMediaSHA256Pattern.MatchString(asset.SHA256) ||
			!releaseKindMatchesContentType(asset.Kind, asset.ContentType) ||
			!nonEmptyReleaseRefs(asset.OwnerRefs) ||
			!nonEmptyReleaseRefs(asset.RightsSnapshotRefs) {
			return nil, fmt.Errorf("release MediaAsset %q is invalid", asset.AssetID)
		}
		expectedSlice := BuildContentMediaPublicSliceKey(asset.Kind, asset.AssetID, asset.Version, asset.ContentType)
		if expectedSlice == "" || asset.PublicSliceKey != expectedSlice {
			return nil, fmt.Errorf("release MediaAsset %q public delivery identity is invalid", asset.AssetID)
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
			return nil, fmt.Errorf("release public media slice is shared by %s and %s", owner, asset.AssetID)
		}
		sliceOwners[asset.PublicSliceKey] = asset.AssetID
		result[asset.AssetID] = asset
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
	expectedSlice := BuildContentMediaPublicSliceKey(asset.Kind, asset.AssetID, asset.Version, asset.ContentType)
	if expectedSlice == "" || asset.PublicSliceKey != expectedSlice {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf("MediaAsset %q public slice is invalid", assetID)
	}
	base := bases.forKind(asset.Kind)
	if base == "" {
		return ResolvedReleaseMediaAsset{}, fmt.Errorf(
			"public media base URL is unavailable for kind %q",
			asset.Kind,
		)
	}
	publicURL := BuildPublicMediaURL(base, asset.PublicSliceKey, asset.Version)
	return ResolvedReleaseMediaAsset{
		ReleaseMediaAsset: asset,
		PublicURL:         publicURL,
		DeliveryRef:       publicURL,
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
	owner := releaseRightsOwner(ref)
	return canonicalReleaseMediaOwnerRef(owner) &&
		canonicalReleaseSourceRef(strings.TrimPrefix(ref, "objects/"+owner+"/"))
}

var releaseSourceRefPattern = regexp.MustCompile(`^sources/[A-Za-z0-9_-]+/source\.json$`)
var releaseSourceEvidencePattern = regexp.MustCompile(`^evidence(?:-[1-9][0-9]*)?\.[A-Za-z0-9]+$`)

func canonicalReleaseSourceRef(ref string) bool {
	return releaseSourceRefPattern.MatchString(ref)
}

func releaseRightsOwner(ref string) string {
	// 从末尾固定三段解析，owner 自身可含名为 sources 的路径段。
	parts := strings.Split(ref, "/")
	if len(parts) < 6 || parts[0] != "objects" ||
		!canonicalReleaseSourceRef(strings.Join(parts[len(parts)-3:], "/")) {
		return ""
	}
	return strings.Join(parts[1:len(parts)-3], "/")
}

func validateReleaseRightsBinding(
	releaseRoot string,
	ref string,
	expectedAssetID string,
	expectedSHA256 string,
) error {
	if !canonicalReleaseRightsRef(ref) {
		return fmt.Errorf("source ref %q is invalid", ref)
	}
	owner := releaseRightsOwner(ref)
	ownerPath := "objects/" + owner + "/"
	name := "manifest.json"
	if strings.HasPrefix(owner, "creators/") {
		name = "profile.json"
	}
	var document struct {
		Assets []struct {
			AssetID    string   `json:"assetId"`
			Path       string   `json:"path"`
			SHA256     string   `json:"sha256"`
			Bytes      int64    `json:"bytes"`
			SourceRefs []string `json:"sourceRefs"`
		} `json:"assets"`
	}
	// owner 的其他字段由其 importer 的完整对象合同校验；这里不复制领域 schema。
	if err := readReleaseMediaDocument(releaseRoot, ownerPath+name, &document, false); err != nil {
		return err
	}
	bound := 0
	for _, asset := range document.Assets {
		if asset.AssetID != expectedAssetID {
			continue
		}
		if asset.SHA256 != expectedSHA256 || asset.Bytes <= 0 ||
			!canonicalReleasePayloadRef(asset.Path) || !strings.HasPrefix(asset.Path, "assets/") {
			return fmt.Errorf("owner %q does not bind MediaAsset identity", owner)
		}
		seen := make(map[string]bool, len(asset.SourceRefs))
		for _, sourceRef := range asset.SourceRefs {
			if !canonicalReleaseSourceRef(sourceRef) || seen[sourceRef] {
				return fmt.Errorf("owner %q contains invalid asset sourceRefs", owner)
			}
			seen[sourceRef] = true
		}
		if !seen[strings.TrimPrefix(ref, ownerPath)] {
			return fmt.Errorf("source %q is not referenced by MediaAsset %q", ref, expectedAssetID)
		}
		bound++
	}
	if bound != 1 {
		return fmt.Errorf("owner %q must uniquely bind MediaAsset %q", owner, expectedAssetID)
	}
	return validateReleaseSource(releaseRoot, ref)
}

type releaseSourceEvidence struct {
	Path   string `json:"path"`
	SHA256 string `json:"sha256"`
	Bytes  int64  `json:"bytes"`
	Kind   string `json:"kind"`
}

func validateReleaseSource(releaseRoot, ref string) error {
	var source struct {
		Schema            string                  `json:"schema"`
		SourceID          string                  `json:"sourceId"`
		SourceURL         string                  `json:"sourceUrl"`
		SourceUseMode     string                  `json:"sourceUseMode"`
		FetchedAt         string                  `json:"fetchedAt"`
		Metadata          map[string]any          `json:"metadata"`
		SourceAttribution map[string]any          `json:"sourceAttribution,omitempty"`
		Assets            []map[string]any        `json:"assets"`
		Evidence          []releaseSourceEvidence `json:"evidence"`
	}
	if err := readReleaseMediaDocument(releaseRoot, ref, &source, true); err != nil {
		return err
	}
	if source.Schema != "quwoquan_data.publish_source" ||
		source.SourceID != path.Base(path.Dir(ref)) ||
		!strings.HasPrefix(source.SourceURL, "https://") || strings.TrimSpace(source.FetchedAt) == "" ||
		source.Metadata == nil || source.Assets == nil || len(source.Evidence) == 0 {
		return fmt.Errorf("source %q contract is invalid", ref)
	}
	switch source.SourceUseMode {
	case "licensed_adaptation", "factual_reference_only", "rights_audit_only":
	default:
		return fmt.Errorf("source %q sourceUseMode is invalid", ref)
	}
	// assets 保留原始权利事实，不把来源存在、访问政策或审计状态推导成新发布许可。
	// 本绑定只证明 owner 的采用关系，不按权利状态创建 release 类别或公开读取门槛。
	for _, asset := range source.Assets {
		if asset == nil {
			return fmt.Errorf("source %q assets must contain objects", ref)
		}
	}
	return validateReleaseSourceEvidenceClosure(releaseRoot, ref, source.Evidence)
}

func validateReleaseSourceEvidenceClosure(releaseRoot, ref string, entries []releaseSourceEvidence) error {
	seen := make(map[string]bool, len(entries))
	for _, evidence := range entries {
		if !releaseSourceEvidencePattern.MatchString(evidence.Path) || seen[evidence.Path] ||
			!releaseMediaSHA256Pattern.MatchString(evidence.SHA256) || evidence.Bytes <= 0 {
			return fmt.Errorf("source %q evidence binding is invalid", ref)
		}
		seen[evidence.Path] = true
		switch evidence.Kind {
		case "source_snapshot", "source_excerpt", "license_response", "acquisition_receipt":
		default:
			return fmt.Errorf("source %q evidence kind is invalid", ref)
		}
		if err := validateReleaseSourceEvidence(releaseRoot, path.Dir(ref)+"/"+evidence.Path, evidence); err != nil {
			return err
		}
	}
	return nil
}

func validateReleaseSourceEvidence(releaseRoot, ref string, evidence releaseSourceEvidence) error {
	file, err := openReleaseMediaFile(releaseRoot, ref)
	if err != nil {
		return err
	}
	defer file.Close()
	digest := sha256.New()
	count, err := io.Copy(digest, file)
	if err != nil || count != evidence.Bytes || fmt.Sprintf("sha256:%x", digest.Sum(nil)) != evidence.SHA256 {
		return fmt.Errorf("source evidence %q bytes or sha256 mismatch", ref)
	}
	return nil
}

func canonicalReleasePayloadRef(ref string) bool {
	return ref != "" && ref != "." && ref != ".." &&
		!strings.HasPrefix(ref, "../") && !strings.Contains(ref, `\`) &&
		!path.IsAbs(ref) && path.Clean(ref) == ref
}

func openReleaseMediaFile(releaseRoot, ref string) (*os.File, error) {
	if !canonicalReleasePayloadRef(ref) {
		return nil, fmt.Errorf("release payload ref %q is invalid", ref)
	}
	current := releaseRoot
	parts := append([]string{"payload"}, strings.Split(ref, "/")...)
	for index, part := range parts {
		current = filepath.Join(current, part)
		info, err := os.Lstat(current)
		if err != nil {
			return nil, fmt.Errorf("read release payload %q: %w", ref, err)
		}
		if info.Mode()&os.ModeSymlink != 0 ||
			(index < len(parts)-1 && !info.IsDir()) ||
			(index == len(parts)-1 && !info.Mode().IsRegular()) {
			return nil, fmt.Errorf("release payload %q must be a regular file without symlinks", ref)
		}
	}
	root, err := os.OpenRoot(filepath.Join(releaseRoot, "payload"))
	if err != nil {
		return nil, err
	}
	defer root.Close()
	return root.Open(filepath.FromSlash(ref))
}

func readReleaseMediaDocument(releaseRoot, ref string, document any, strict bool) error {
	file, err := openReleaseMediaFile(releaseRoot, ref)
	if err != nil {
		return err
	}
	defer file.Close()
	if err := decodeReleaseMediaDocument(file, document, strict); err != nil {
		return fmt.Errorf("decode release document %q: %w", ref, err)
	}
	return nil
}

func decodeReleaseMediaDocument(reader io.Reader, document any, strict bool) error {
	decoder := json.NewDecoder(reader)
	if strict {
		decoder.DisallowUnknownFields()
	}
	if err := decoder.Decode(document); err != nil {
		return err
	}
	if err := decoder.Decode(new(any)); err != io.EOF {
		return fmt.Errorf("release document must contain exactly one JSON value")
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
	if !canonicalReleaseMediaOwnerRef(ownerRef) {
		return false
	}
	for _, raw := range refs {
		ref := strings.TrimSpace(raw)
		if canonicalReleaseRightsRef(ref) && releaseRightsOwner(ref) == ownerRef {
			return true
		}
	}
	return false
}
