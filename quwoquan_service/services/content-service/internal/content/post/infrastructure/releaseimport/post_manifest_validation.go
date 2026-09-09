package releaseimport

import (
	"bytes"
	"encoding/json"
	"fmt"
	"slices"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
)

type postManifest struct {
	ContentID             string                             `json:"contentId"`
	Version               int64                              `json:"version"`
	PoolSourceType        string                             `json:"sourceType"`
	VariantPurpose        string                             `json:"variantPurpose"`
	Admission             ContentAdmission                   `json:"admission"`
	PoolStatus            string                             `json:"status"`
	ContentType           string                             `json:"contentType"`
	ContentIdentity       string                             `json:"contentIdentity"`
	Title                 string                             `json:"title"`
	Caption               string                             `json:"caption"`
	DisplayTitle          string                             `json:"displayTitle"`
	Body                  string                             `json:"body"`
	EntityRefs            []string                           `json:"entityRefs"`
	NormalizedEntityRefs  []string                           `json:"normalizedEntityRefs"`
	TagRefs               []string                           `json:"tagRefs"`
	IntersectionHints     []IntersectionHintDoc              `json:"intersectionHints"`
	SemanticMentions      []postmodel.PostSemanticMention    `json:"semanticMentions"`
	AuthorID              string                             `json:"authorId"`
	CreatorProfileID      string                             `json:"creatorProfileId"`
	CreatorArchetype      string                             `json:"creatorArchetype"`
	CreatorProfileVersion string                             `json:"creatorProfileVersion"`
	CreatorProfileDigest  string                             `json:"creatorProfileDigest"`
	CreatorDisclosure     postmodel.PostCreatorDisclosure    `json:"creatorDisclosure"`
	ExperienceClaimMode   string                             `json:"experienceClaimMode"`
	AuthorQualitySignals  postmodel.PostAuthorQualitySignals `json:"authorQualitySignals"`
	Assets                []AssetManifestItem                `json:"assets"`
	SourceCollectionID    string                             `json:"sourceCollectionId"`
	SourcePlatform        string                             `json:"sourcePlatform"`
	SourceAttribution     postmodel.SourceAttribution        `json:"sourceAttribution"`
	Creator               any                                `json:"creator"`
	Page                  any                                `json:"page"`
	LicenseProof          any                                `json:"licenseProof"`
	SourceCreator         string                             `json:"sourceCreator"`
	SourceCollectionURL   string                             `json:"sourceCollectionUrl"`
	LicenseProofRef       string                             `json:"licenseProofRef"`
	Template              string                             `json:"template"`
	ArticleDigest         string                             `json:"articleMarkdownDigest"`
	PublishTitle          string                             `json:"publishTitle"`
	PublishAngle          string                             `json:"publishAngle"`
	PublishSeq            int                                `json:"publishSeq"`
	ArticleAssetManifest  *ArticleAssetManifestDoc           `json:"articleAssetManifest"`
	CreatedAt             string                             `json:"createdAt"`
	UpdatedAt             string                             `json:"updatedAt"`
	PublishedAt           string                             `json:"publishedAt"`
}

// decodeReleaseSourceAttribution 不让 encoding/json 静默丢弃退休字段或新修改事实。
func decodeReleaseSourceAttribution(raw []byte, ref string) (postmodel.SourceAttribution, error) {
	var envelope struct {
		SourceAttribution json.RawMessage `json:"sourceAttribution"`
	}
	if err := json.Unmarshal(raw, &envelope); err != nil {
		return postmodel.SourceAttribution{}, err
	}
	var attribution postmodel.SourceAttribution
	if len(envelope.SourceAttribution) == 0 {
		return attribution, nil
	}
	if err := validateReleaseSourceFacts(envelope.SourceAttribution); err != nil {
		return attribution, fmt.Errorf("%s: sourceAttribution: %w", ref, err)
	}
	decoder := json.NewDecoder(bytes.NewReader(envelope.SourceAttribution))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&attribution); err != nil {
		return attribution, fmt.Errorf("%s: sourceAttribution: %w", ref, err)
	}
	if attribution.PublicationAdmission != "production_release" || attribution.DerivedModifications == nil {
		return attribution, fmt.Errorf("%s: sourceAttribution requires production_release and explicit derivedModifications", ref)
	}
	seen := make(map[string]bool)
	for _, modification := range attribution.DerivedModifications {
		switch modification {
		case "video_frame_extraction", "crop", "resize", "format_conversion":
		default:
			return attribution, fmt.Errorf("%s: sourceAttribution derivedModifications is invalid", ref)
		}
		if seen[modification] {
			return attribution, fmt.Errorf("%s: sourceAttribution derivedModifications contains duplicates", ref)
		}
		seen[modification] = true
	}
	switch attribution.WatermarkKind {
	case "", "none", "author_signature", "platform_logo", "stock_agency", "other", "unknown":
	default:
		return attribution, fmt.Errorf("%s: sourceAttribution watermarkKind is invalid", ref)
	}
	return attribution, nil
}

// validateReleaseSourceFacts 对齐 Data post_manifest.schema.json 的 sourceAttribution：
// Go 零值不能替代必填事实；可选水印事实允许缺席，但显式 null 不合法。
func validateReleaseSourceFacts(raw []byte) error {
	var facts map[string]json.RawMessage
	if err := json.Unmarshal(raw, &facts); err != nil {
		return err
	}
	for _, name := range []string{
		"isOriginal", "originalCreatorName", "platform", "sourcePostUrl", "originalAssetUrl",
		"attributionText", "rightsBasis", "commercialAuthorizationStatus", "publicationAdmission",
		"watermarkStatus", "audioRightsStatus", "modelReleaseStatus", "propertyReleaseStatus",
		"collectedAt", "takedownPolicy", "derivedModifications",
	} {
		value, exists := facts[name]
		if !exists || bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
			return fmt.Errorf("%s is required and must not be null", name)
		}
		if name == "isOriginal" || name == "derivedModifications" {
			continue
		}
		var text string
		if err := json.Unmarshal(value, &text); err != nil || text == "" {
			return fmt.Errorf("%s must be a non-empty string", name)
		}
	}
	for _, name := range []string{"watermarkKind", "watermarkNote"} {
		if value, exists := facts[name]; exists && bytes.Equal(bytes.TrimSpace(value), []byte("null")) {
			return fmt.Errorf("%s must not be null when present", name)
		}
	}
	for name, allowed := range map[string][]string{
		"commercialAuthorizationStatus": {"verified", "unverified"},
		"watermarkStatus":               {"absent", "present", "unknown"},
		"audioRightsStatus":             {"licensed", "original_authorized", "replaced_with_licensed_track", "no_audio", "unverified"},
		"watermarkKind":                 {"none", "author_signature", "platform_logo", "stock_agency", "other", "unknown"},
	} {
		rawValue, exists := facts[name]
		if !exists {
			continue
		}
		var value string
		if err := json.Unmarshal(rawValue, &value); err != nil || !slices.Contains(allowed, value) {
			return fmt.Errorf("%s is outside the Data source fact enum", name)
		}
	}
	return nil
}

type ContentAdmission struct {
	ProcessResult  string `json:"processResult" bson:"processResult"`
	QualityResult  string `json:"qualityResult" bson:"qualityResult"`
	UsageScope     string `json:"usageScope" bson:"usageScope"`
	EvidenceRef    string `json:"evidenceRef" bson:"evidenceRef"`
	EvidenceDigest string `json:"evidenceDigest" bson:"evidenceDigest"`
}

func normalizeImportedContentPoolRecord(m *postManifest, postRef string) error {
	if strings.TrimSpace(m.ContentID) == "" || m.Version < 1 ||
		m.PoolSourceType != "data" || m.PoolStatus != "active" ||
		m.Admission.ProcessResult != "completed" || m.Admission.QualityResult != "passed" ||
		!sha256Pattern.MatchString(strings.TrimSpace(m.Admission.EvidenceDigest)) ||
		strings.TrimSpace(m.Admission.EvidenceRef) == "" {
		return fmt.Errorf("%s: canonical content pool admission is incomplete", postRef)
	}
	if m.VariantPurpose != "original" && m.VariantPurpose != "commercial_variant" {
		return fmt.Errorf("%s: canonical content variantPurpose is invalid", postRef)
	}
	if m.Admission.UsageScope != "production" {
		return fmt.Errorf("%s: canonical content usageScope must be production", postRef)
	}
	return nil
}

func parseManifestTime(ref string, field string, raw string) (time.Time, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return time.Time{}, fmt.Errorf("%s: manifest missing %s", ref, field)
	}
	parsed, err := time.Parse(time.RFC3339, value)
	if err != nil {
		return time.Time{}, fmt.Errorf("%s: invalid %s %q: %w", ref, field, value, err)
	}
	return parsed.UTC(), nil
}

func parseOptionalManifestTime(ref string, field string, raw string, fallback time.Time) (time.Time, error) {
	if strings.TrimSpace(raw) == "" {
		return fallback, nil
	}
	return parseManifestTime(ref, field, raw)
}

func validateAssetItem(asset AssetManifestItem, ref string) error {
	if strings.TrimSpace(asset.AssetID) == "" {
		return fmt.Errorf("%s: asset manifest missing assetId", ref)
	}
	objectKey := strings.TrimSpace(asset.ObjectKey)
	if objectKey != "" {
		return fmt.Errorf(
			"%s: release asset manifest must not expose private objectKey",
			ref,
		)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(asset.Sha256)) {
		return fmt.Errorf("%s: asset manifest sha256 invalid", ref)
	}
	if asset.SourceOriginalSha256 != "" && !sha256Pattern.MatchString(strings.TrimSpace(asset.SourceOriginalSha256)) {
		return fmt.Errorf("%s: asset manifest sourceOriginalSha256 invalid", ref)
	}
	return nil
}

// validateReleaseMediaDeliveryContract 在 immutable release 导入边界锁定新投影的
// typed 交付语义（REQ-016/GWT-032）。legacy public 兼容只能位于 App 的具名
// migration adapter；新 release 不得以缺席 accessMode、URL 形态或路径后缀猜 public。
func validateReleaseMediaDeliveryContract(
	assets []AssetManifestItem,
	releaseClass string,
	ref string,
) error {
	expectedMode := MediaDeliveryAccessModeForReleaseClass(releaseClass)
	if expectedMode == "" {
		return fmt.Errorf("%s: releaseClass must explicitly select a media accessMode", ref)
	}
	for _, asset := range assets {
		assetID := strings.TrimSpace(asset.AssetID)
		mode := strings.TrimSpace(asset.AccessMode)
		if assetID == "" || mode != MediaDeliveryAccessModePublic {
			return fmt.Errorf("%s: media asset %q requires assetId and accessMode must be public", ref, assetID)
		}
		if mode != expectedMode {
			return fmt.Errorf(
				"%s: media asset %q accessMode %q differs from releaseClass %q",
				ref,
				assetID,
				mode,
				releaseClass,
			)
		}
	}
	return nil
}

// ValidateImportedPostMediaBindings runs after release-authority binding and
// before any Post/read-model write. It proves every projected media item and
// article asset has the releaseClass-selected typed mode; raw authoring
// manifests are not a legacy escape hatch.
func ValidateImportedPostMediaBindings(posts []PostDoc, releaseClass string) error {
	if MediaDeliveryAccessModeForReleaseClass(releaseClass) == "" {
		return fmt.Errorf("releaseClass must be production")
	}
	for _, post := range posts {
		assets := importedPostAssets(post)
		if err := validateReleaseMediaDeliveryContract(assets, releaseClass, post.PostRef); err != nil {
			return err
		}
		if post.ArticleAssetManifest != nil {
			if err := validateReleaseMediaDeliveryContract(
				post.ArticleAssetManifest.Assets,
				releaseClass,
				post.PostRef+" articleAssetManifest",
			); err != nil {
				return err
			}
		}
	}
	return nil
}

func parseRightsAuditStatus(raw string) (RightsAuditStatus, error) {
	status := RightsAuditStatus(strings.TrimSpace(raw))
	switch status {
	case RightsAuditStatusVerified, RightsAuditStatusUnverified, RightsAuditStatusUnknown, RightsAuditStatusRestricted:
		return status, nil
	default:
		return "", fmt.Errorf("rightsAuditStatus must be verified, unverified, unknown or restricted")
	}
}

func hasNonEmptyString(values []string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return true
		}
	}
	return false
}

func validateImageAssets(assets []AssetManifestItem, sourceCollectionID string, ref string, releaseClass string) error {
	if len(assets) == 0 || len(assets) > 20 {
		return fmt.Errorf("%s: image manifest assets must contain 1..20 items", ref)
	}
	if strings.TrimSpace(sourceCollectionID) == "" {
		return fmt.Errorf("%s: image manifest missing sourceCollectionId", ref)
	}
	for _, asset := range assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
		if asset.SourceCollectionID != sourceCollectionID {
			return fmt.Errorf("%s: image asset sourceCollectionId does not match work manifest", ref)
		}
		if strings.TrimSpace(asset.Creator) == "" || strings.TrimSpace(asset.CollectionPageURL) == "" {
			return fmt.Errorf("%s: image asset missing creator or collectionPageUrl", ref)
		}
		status, err := parseRightsAuditStatus(asset.RightsAuditStatus)
		if err != nil {
			return fmt.Errorf("%s: image asset %q %w", ref, asset.AssetID, err)
		}
		switch status {
		case RightsAuditStatusVerified:
			if strings.TrimSpace(asset.License) == "" ||
				(strings.TrimSpace(asset.TermsURL) == "" && strings.TrimSpace(asset.AuthorizationProof) == "") {
				return fmt.Errorf("%s: verified image asset %q missing license or proof", ref, asset.AssetID)
			}
			if hasNonEmptyString(asset.RightsAuditIssues) {
				return fmt.Errorf("%s: verified image asset %q has audit issues", ref, asset.AssetID)
			}
		case RightsAuditStatusUnverified, RightsAuditStatusUnknown, RightsAuditStatusRestricted:
			// 授权核验状态仍是事实；production 不将未核验改写为已授权。
			if releaseClass != "production" {
				return fmt.Errorf(
					"%s: unverified image asset %q cannot enter an immutable release",
					ref,
					asset.AssetID,
				)
			}
			if strings.TrimSpace(asset.License) == "" ||
				(strings.TrimSpace(asset.TermsURL) == "" && strings.TrimSpace(asset.AuthorizationProof) == "") {
				return fmt.Errorf(
					"%s: unverified image asset %q missing license or proof",
					ref,
					asset.AssetID,
				)
			}
		}
	}
	return nil
}

func validateVideoAssets(assets []AssetManifestItem, ref string, releaseClass string) error {
	byID := make(map[string]AssetManifestItem, len(assets))
	for _, asset := range assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
		status, err := parseRightsAuditStatus(asset.RightsAuditStatus)
		if err != nil {
			return fmt.Errorf("%s: video asset %q %w", ref, asset.AssetID, err)
		}
		if status != RightsAuditStatusVerified || hasNonEmptyString(asset.RightsAuditIssues) {
			// production 类别（DEC-041）接受未完成商用核验的视频资产作为记录事实，
			// 但许可链字段必须在场；其它类别保持 fail closed。
			if releaseClass != "production" {
				return fmt.Errorf(
					"%s: video asset %q must be commercially verified without issues",
					ref,
					asset.AssetID,
				)
			}
			if strings.TrimSpace(asset.License) == "" ||
				(strings.TrimSpace(asset.TermsURL) == "" && strings.TrimSpace(asset.AuthorizationProof) == "") {
				return fmt.Errorf("%s: production unverified video asset %q missing license or proof", ref, asset.AssetID)
			}
		}
		if _, exists := byID[asset.AssetID]; exists {
			return fmt.Errorf("%s: duplicate assetId %q", ref, asset.AssetID)
		}
		byID[asset.AssetID] = asset
	}
	hasVideo := false
	for _, asset := range assets {
		if !strings.EqualFold(strings.TrimSpace(asset.Kind), "video") {
			continue
		}
		hasVideo = true
		posterID := strings.TrimSpace(asset.PosterAssetID)
		poster, exists := byID[posterID]
		if posterID == "" || !exists {
			return fmt.Errorf("%s: video asset %q posterAssetId does not resolve", ref, asset.AssetID)
		}
		if !strings.EqualFold(strings.TrimSpace(poster.Kind), "image") ||
			!strings.EqualFold(strings.TrimSpace(poster.Role), "cover") {
			return fmt.Errorf("%s: video poster %q must be an image cover asset", ref, posterID)
		}
	}
	if !hasVideo {
		return fmt.Errorf("%s: video manifest requires a video asset", ref)
	}
	return nil
}

func BindPostAssetURLs(
	posts []PostDoc,
	releaseAssets map[string]ReleaseMediaAsset,
	mediaBases runtimemedia.MediaDeliveryBases,
) error {
	hasAssets := false
	for _, post := range posts {
		if len(post.Assets) > 0 {
			hasAssets = true
			break
		}
	}
	if !hasAssets {
		return nil
	}
	for postIndex := range posts {
		assets := posts[postIndex].Assets
		byID := make(map[string]*AssetManifestItem, len(assets))
		for assetIndex := range assets {
			asset := &assets[assetIndex]
			kind := strings.ToLower(strings.TrimSpace(asset.Kind))
			if kind == "" {
				if releaseAsset, exists := releaseAssets[asset.AssetID]; exists {
					kind = releaseAsset.Kind
				}
			}
			resolved, err := runtimemedia.ResolveReleaseMediaAsset(
				releaseAssets,
				mediaBases,
				asset.AssetID,
				kind,
				asset.Sha256,
				posts[postIndex].PostRef,
			)
			if err != nil {
				return fmt.Errorf(
					"%s: asset %q identity differs from release media authority: %w",
					posts[postIndex].PostRef,
					asset.AssetID,
					err,
				)
			}
			asset.Kind = kind
			asset.Version = resolved.Version
			asset.PublicSliceKey = resolved.PublicSliceKey
			// Data release authority 只接受 production public slice。
			asset.AccessMode = MediaDeliveryAccessModePublic
			asset.CDNURL = resolved.DeliveryRef
			asset.ObjectKey = ""
			byID[asset.AssetID] = asset
		}
		for assetIndex := range assets {
			asset := &assets[assetIndex]
			if !strings.EqualFold(strings.TrimSpace(asset.Kind), "video") {
				continue
			}
			poster := byID[asset.PosterAssetID]
			if poster == nil || poster.CDNURL == "" {
				return fmt.Errorf("%s: video poster URL cannot be resolved", posts[postIndex].PostRef)
			}
			asset.ThumbnailURL = poster.CDNURL
			asset.CoverURL = poster.CDNURL
		}
		posts[postIndex].Assets = assets
		if posts[postIndex].ArticleAssetManifest != nil {
			posts[postIndex].ArticleAssetManifest.Assets = append(
				[]AssetManifestItem(nil),
				assets...,
			)
		}
	}
	return nil
}

func ValidateArticleAssetManifest(manifest *ArticleAssetManifestDoc, ref string) error {
	if manifest == nil {
		return nil
	}
	if manifest.Schema != ArticleAssetManifestSchema {
		return fmt.Errorf(
			"%s: articleAssetManifest.schema must be %q, got %q",
			ref,
			ArticleAssetManifestSchema,
			manifest.Schema,
		)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.ArticleMarkdownDigest)) {
		return fmt.Errorf("%s: articleAssetManifest.articleMarkdownDigest invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.DocumentSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.documentSha256 invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.AssetManifestSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.assetManifestSha256 invalid", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(manifest.DocumentVersionSha256)) {
		return fmt.Errorf("%s: articleAssetManifest.documentVersionSha256 invalid", ref)
	}
	for _, asset := range manifest.Assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
	}
	return nil
}

func validateIntersectionHints(hints []IntersectionHintDoc, entityRefs []string, tagRefs []string, ref string) error {
	if len(hints) == 0 {
		return nil
	}
	allowedDimensions := map[string]bool{
		"identity": true, "location": true, "content": true, "interest": true, "relationship": true,
	}
	allowedSources := map[string]bool{
		"tagRef": true, "geoTagRef": true, "entityRef": true, "relationship": true, "contact": true,
	}
	allowedActions := map[string]bool{
		"follow": true, "join": true, "add_contact": true, "view_object": true,
	}
	entitySet := map[string]bool{}
	for _, entityRef := range entityRefs {
		entitySet[strings.TrimSpace(entityRef)] = true
	}
	tagSet := map[string]bool{}
	for _, tagRef := range tagRefs {
		tagSet[strings.TrimSpace(tagRef)] = true
	}
	for idx, hint := range hints {
		label := fmt.Sprintf("%s: intersectionHints[%d]", ref, idx)
		if !allowedDimensions[strings.TrimSpace(hint.Dimension)] {
			return fmt.Errorf("%s dimension invalid: %q", label, hint.Dimension)
		}
		source := strings.TrimSpace(hint.Source)
		if !allowedSources[source] {
			return fmt.Errorf("%s source invalid: %q", label, hint.Source)
		}
		if !allowedActions[strings.TrimSpace(hint.ActionType)] {
			return fmt.Errorf("%s actionType invalid: %q", label, hint.ActionType)
		}
		actionTargetID := strings.TrimSpace(hint.ActionTargetID)
		if actionTargetID == "" {
			return fmt.Errorf("%s actionTargetId is required", label)
		}
		switch source {
		case "entityRef":
			if !entitySet[actionTargetID] {
				return fmt.Errorf("%s entityRef target not in manifest entity refs: %q", label, actionTargetID)
			}
		case "tagRef", "geoTagRef":
			if len(hint.TagRefs) == 0 {
				return fmt.Errorf("%s %s requires tagRefs", label, source)
			}
			for _, tagRef := range hint.TagRefs {
				tagRef = strings.TrimSpace(tagRef)
				if !tagSet[tagRef] {
					return fmt.Errorf("%s tagRef not in manifest tagRefs: %q", label, tagRef)
				}
			}
		}
	}
	return nil
}

func systemAuthorManifest(m postManifest) bool {
	authorID := strings.TrimSpace(m.AuthorID)
	creatorProfileID := strings.TrimSpace(m.CreatorProfileID)
	return strings.HasPrefix(authorID, "agent_author_") || strings.HasPrefix(authorID, "builtin_") ||
		strings.HasPrefix(creatorProfileID, "agent_creator_") ||
		strings.HasPrefix(creatorProfileID, "qwq_creator_")
}

// resolveCreatorProfileVersion binds the runtime creatorProfileVersion field.
// Canonical release manifests pin creators with content-addressed
// creatorProfileDigest; that digest is the authoritative profile binding and
// is accepted when creatorProfileVersion is omitted.
func resolveCreatorProfileVersion(m *postManifest) string {
	if m == nil {
		return ""
	}
	if version := strings.TrimSpace(m.CreatorProfileVersion); version != "" {
		return version
	}
	if digest := strings.TrimSpace(m.CreatorProfileDigest); digest != "" {
		m.CreatorProfileVersion = digest
		return digest
	}
	return ""
}

func validateCreatorProjection(m postManifest, ref string) error {
	if !systemAuthorManifest(m) {
		return nil
	}
	if strings.TrimSpace(m.AuthorID) == "" {
		return fmt.Errorf("%s: system creator manifest missing authorId", ref)
	}
	if strings.TrimSpace(m.CreatorProfileID) == "" {
		return fmt.Errorf("%s: system creator manifest missing creatorProfileId", ref)
	}
	if strings.TrimSpace(m.CreatorArchetype) == "" {
		return fmt.Errorf("%s: system creator manifest missing creatorArchetype", ref)
	}
	if strings.TrimSpace(m.CreatorProfileVersion) == "" {
		return fmt.Errorf("%s: system creator manifest missing creatorProfileVersion or creatorProfileDigest", ref)
	}
	if strings.TrimSpace(m.ExperienceClaimMode) == "" {
		return fmt.Errorf("%s: system creator manifest missing experienceClaimMode", ref)
	}
	if strings.TrimSpace(m.CreatorDisclosure.Type) == "" {
		return fmt.Errorf("%s: system creator manifest missing creatorDisclosure", ref)
	}
	if m.CreatorDisclosure.Type != "platform_virtual_creator" {
		return fmt.Errorf("%s: creatorDisclosure.type must be platform_virtual_creator", ref)
	}
	if !m.CreatorDisclosure.Visible {
		return fmt.Errorf("%s: creatorDisclosure.visible must be true", ref)
	}
	if strings.TrimSpace(m.CreatorDisclosure.DisplayText) == "" {
		return fmt.Errorf("%s: creatorDisclosure.displayText is required", ref)
	}
	return nil
}

func validateEntityAssetManifest(manifest *EntityAssetManifestDoc, ref string) error {
	if manifest == nil {
		return nil
	}
	for _, asset := range manifest.Assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
		}
	}
	return nil
}

func canonicalImportedContentIdentity(raw string) (string, error) {
	identity := strings.ToLower(strings.TrimSpace(raw))
	if identity == "" {
		return "", fmt.Errorf("canonical release post contentIdentity is required")
	}
	if identity != "work" {
		return "", fmt.Errorf("canonical release post contentIdentity must be work")
	}
	return identity, nil
}
