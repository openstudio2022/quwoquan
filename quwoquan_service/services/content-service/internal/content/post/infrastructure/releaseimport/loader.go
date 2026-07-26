// Package releaseimport implements the pure immutable-release loading layer.
//
// 唯一内容真相源是自治 canonical object package；选择集只来自 immutable release
// payload/desired_state.json。禁止 sample bundle fallback 或无 release 的全树导入。
package releaseimport

import (
	"encoding/json"
	"fmt"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

const ArticleAssetManifestSchema = "article-asset-manifest"

type RightsAuditStatus string

const (
	RightsAuditStatusVerified   RightsAuditStatus = "verified"
	RightsAuditStatusUnverified RightsAuditStatus = "unverified"
)

var (
	sha256Pattern       = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	casObjectKeyPattern = regexp.MustCompile(`^media/objects/sha256/[0-9a-f]{2}/[0-9a-f]{2}/[0-9a-f]{64}\.[A-Za-z0-9]+$`)
)

type AssetManifestItem struct {
	AssetID              string   `json:"assetId" bson:"assetId"`
	Kind                 string   `json:"kind,omitempty" bson:"kind,omitempty"`
	ObjectKey            string   `json:"objectKey" bson:"objectKey"`
	CDNURL               string   `json:"cdnUrl,omitempty" bson:"cdnUrl,omitempty"`
	Sha256               string   `json:"sha256" bson:"sha256"`
	MimeType             string   `json:"mimeType,omitempty" bson:"mimeType,omitempty"`
	SourceOriginalSha256 string   `json:"sourceOriginalSha256,omitempty" bson:"sourceOriginalSha256,omitempty"`
	Caption              string   `json:"caption,omitempty" bson:"caption,omitempty"`
	Role                 string   `json:"role,omitempty" bson:"role,omitempty"`
	Width                int64    `json:"width,omitempty" bson:"width,omitempty"`
	Height               int64    `json:"height,omitempty" bson:"height,omitempty"`
	DurationMs           int64    `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	ThumbnailURL         string   `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	CoverURL             string   `json:"coverUrl,omitempty" bson:"coverUrl,omitempty"`
	CoverStrategy        string   `json:"coverStrategy,omitempty" bson:"coverStrategy,omitempty"`
	CoverFrameTimeMs     int64    `json:"coverFrameTimeMs,omitempty" bson:"coverFrameTimeMs,omitempty"`
	PosterAssetID        string   `json:"posterAssetId,omitempty" bson:"posterAssetId,omitempty"`
	SourceCollectionID   string   `json:"sourceCollectionId,omitempty" bson:"sourceCollectionId,omitempty"`
	Creator              string   `json:"creator,omitempty" bson:"creator,omitempty"`
	CollectionPageURL    string   `json:"collectionPageUrl,omitempty" bson:"collectionPageUrl,omitempty"`
	License              string   `json:"license,omitempty" bson:"license,omitempty"`
	TermsURL             string   `json:"termsUrl,omitempty" bson:"termsUrl,omitempty"`
	AuthorizationProof   string   `json:"authorizationProof,omitempty" bson:"authorizationProof,omitempty"`
	RightsAuditStatus    string   `json:"rightsAuditStatus,omitempty" bson:"rightsAuditStatus,omitempty"`
	RightsAuditIssues    []string `json:"rightsAuditIssues,omitempty" bson:"rightsAuditIssues,omitempty"`
}

type ArticleAssetManifestDoc struct {
	Schema                string              `json:"schema" bson:"schema"`
	MarkdownDialect       string              `json:"markdownDialect,omitempty" bson:"markdownDialect,omitempty"`
	ArticleMarkdownDigest string              `json:"articleMarkdownDigest" bson:"articleMarkdownDigest"`
	DocumentSha256        string              `json:"documentSha256" bson:"documentSha256"`
	AssetManifestSha256   string              `json:"assetManifestSha256" bson:"assetManifestSha256"`
	DocumentVersionSha256 string              `json:"documentVersionSha256" bson:"documentVersionSha256"`
	Assets                []AssetManifestItem `json:"assets" bson:"assets"`
}

type EntityAssetManifestDoc struct {
	Assets []AssetManifestItem `json:"assets" bson:"assets"`
}

type IntersectionHintDoc struct {
	Dimension      string   `json:"dimension" bson:"dimension"`
	Source         string   `json:"source" bson:"source"`
	TagRefs        []string `json:"tagRefs" bson:"tagRefs"`
	ActionType     string   `json:"actionType" bson:"actionType"`
	ActionTargetID string   `json:"actionTargetId" bson:"actionTargetId"`
}

// PostDoc 是灌入运行库的文章文档（与 publish post manifest + article.md 对齐）。
type PostDoc struct {
	PostRef               string                   `json:"postRef" bson:"postRef"`
	ContentType           string                   `json:"contentType" bson:"contentType"`
	Title                 string                   `json:"title" bson:"title"`
	Body                  string                   `json:"body" bson:"body"`
	Angle                 string                   `json:"angle" bson:"angle"`
	Seq                   int                      `json:"seq" bson:"seq"`
	EntityRefs            []string                 `json:"entityRefs" bson:"entityRefs"`
	NormalizedEntityRefs  []string                 `json:"normalizedEntityRefs" bson:"normalizedEntityRefs"`
	TagRefs               []string                 `json:"tagRefs" bson:"tagRefs"`
	IntersectionHints     []IntersectionHintDoc    `json:"intersectionHints" bson:"intersectionHints"`
	SemanticMentions      any                      `json:"semanticMentions" bson:"semanticMentions"`
	AuthorID              string                   `json:"authorId" bson:"authorId"`
	CreatorProfileID      string                   `json:"creatorProfileId" bson:"creatorProfileId"`
	CreatorArchetype      string                   `json:"creatorArchetype" bson:"creatorArchetype"`
	CreatorProfileVersion string                   `json:"creatorProfileVersion" bson:"creatorProfileVersion"`
	CreatorDisclosure     map[string]any           `json:"creatorDisclosure" bson:"creatorDisclosure"`
	ExperienceClaimMode   string                   `json:"experienceClaimMode" bson:"experienceClaimMode"`
	AuthorQualitySignals  map[string]any           `json:"authorQualitySignals" bson:"authorQualitySignals"`
	Assets                []AssetManifestItem      `json:"assets" bson:"assets"`
	SourceCollectionID    string                   `json:"sourceCollectionId" bson:"sourceCollectionId"`
	SourcePlatform        string                   `json:"sourcePlatform" bson:"sourcePlatform"`
	Creator               any                      `json:"creator" bson:"creator"`
	Page                  any                      `json:"page" bson:"page"`
	LicenseProof          any                      `json:"licenseProof" bson:"licenseProof"`
	Template              string                   `json:"template" bson:"template"`
	GeneratorModel        string                   `json:"generatorModel" bson:"generatorModel"`
	ArticleMarkdown       string                   `json:"articleMarkdown" bson:"articleMarkdown"`
	ArticleDigest         string                   `json:"articleDigest" bson:"articleDigest"`
	ArticleAssetManifest  *ArticleAssetManifestDoc `json:"articleAssetManifest" bson:"articleAssetManifest"`
	SourceTaskId          string                   `json:"sourceTaskId" bson:"sourceTaskId"`
	CreatedAt             time.Time                `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time                `json:"updatedAt" bson:"updatedAt"`
	PublishedAt           time.Time                `json:"publishedAt" bson:"publishedAt"`
}

// EntityDoc 是灌入运行库的实体文档（与 publish entity _entity.json + page.md 对齐）。
type EntityDoc struct {
	EntityRef     string                  `json:"entityRef" bson:"entityRef"`
	Domain        string                  `json:"domain" bson:"domain"`
	Etype         string                  `json:"etype" bson:"etype"`
	Name          string                  `json:"name" bson:"name"`
	Label         string                  `json:"label" bson:"label"`
	TagRefs       []string                `json:"tagRefs" bson:"tagRefs"`
	Page          string                  `json:"page" bson:"page"`
	HasPage       bool                    `json:"hasPage" bson:"hasPage"`
	AssetManifest *EntityAssetManifestDoc `json:"assetManifest" bson:"assetManifest"`
	// ConditionProfile 条件画像（L3 实体级 {regions/seasons/altitudeMeters}），从 _entity.json 透传到运行库。
	ConditionProfile map[string]any `json:"conditionProfile" bson:"conditionProfile"`
	SourceTaskId     string         `json:"sourceTaskId" bson:"sourceTaskId"`
}

type ReleaseDesiredState struct {
	Schema      string `json:"schema"`
	ReleaseID   string `json:"releaseId"`
	DesiredRefs struct {
		Creators []string `json:"creators"`
		Posts    []string `json:"posts"`
		Entities []string `json:"entities"`
	} `json:"desiredRefs"`
}

type creatorProfileDoc struct {
	Schema    string `json:"schema"`
	CreatorID string `json:"creatorId"`
	UserID    string `json:"userId"`
	AuthorID  string `json:"authorId"`
}

type creatorImportReceipt struct {
	Schema      string   `json:"schema"`
	Status      string   `json:"status"`
	ReleaseID   string   `json:"releaseId"`
	SourceOwner string   `json:"sourceOwner"`
	AuthorIDs   []string `json:"authorIds"`
}

func ReleaseObjectRoot(releaseRoot string) (string, error) {
	root := filepath.Join(releaseRoot, "payload", "objects")
	info, err := os.Stat(root)
	if err != nil {
		return "", fmt.Errorf("release object closure unavailable: %s: %w", root, err)
	}
	if !info.IsDir() {
		return "", fmt.Errorf("release object closure is not a directory: %s", root)
	}
	return root, nil
}

func LoadReleaseDesiredState(releaseRoot string) (*ReleaseDesiredState, error) {
	path := filepath.Join(releaseRoot, "payload", "desired_state.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var desired ReleaseDesiredState
	if err := json.Unmarshal(raw, &desired); err != nil {
		return nil, err
	}
	if desired.Schema != "quwoquan_data.release_desired_state" {
		return nil, fmt.Errorf(
			"%s: unsupported release schema %q",
			path,
			desired.Schema,
		)
	}
	if strings.TrimSpace(desired.ReleaseID) == "" {
		return nil, fmt.Errorf("%s: releaseId is required", path)
	}
	for _, ref := range append(
		append(append([]string(nil), desired.DesiredRefs.Creators...), desired.DesiredRefs.Posts...),
		desired.DesiredRefs.Entities...,
	) {
		clean := filepath.Clean(filepath.FromSlash(ref))
		if ref == "" || filepath.IsAbs(clean) || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
			return nil, fmt.Errorf("%s: unsafe desired ref %q", path, ref)
		}
	}
	return &desired, nil
}

// LoadCreatorAuthorIDs makes the release's public-author closure explicit for
// content import. A post can never be materialized before its author profile
// has been imported by user-service.
func LoadCreatorAuthorIDs(objectRoot string, filter map[string]bool) (map[string]bool, error) {
	authors := make(map[string]bool, len(filter))
	for ref := range filter {
		path := filepath.Join(objectRoot, "creators", filepath.FromSlash(ref), "profile.json")
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("creator profile missing for %s: %w", ref, err)
		}
		var profile creatorProfileDoc
		if err := json.Unmarshal(raw, &profile); err != nil {
			return nil, fmt.Errorf("decode creator profile %s: %w", ref, err)
		}
		if profile.Schema != "quwoquan_data.creator_profile" || profile.CreatorID != ref ||
			strings.TrimSpace(profile.AuthorID) == "" || profile.UserID != profile.AuthorID {
			return nil, fmt.Errorf("creator profile invalid: %s", ref)
		}
		if authors[profile.AuthorID] {
			return nil, fmt.Errorf("creator authorId is duplicated: %s", profile.AuthorID)
		}
		authors[profile.AuthorID] = true
	}
	return authors, nil
}

func ValidateCreatorImportReceipt(path, releaseID string, expectedAuthors map[string]bool) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read creator import receipt: %w", err)
	}
	var receipt creatorImportReceipt
	if err := json.Unmarshal(raw, &receipt); err != nil {
		return fmt.Errorf("decode creator import receipt: %w", err)
	}
	if receipt.Schema != "quwoquan.user_creator_import_report" ||
		receipt.ReleaseID != releaseID || receipt.SourceOwner != "qwq_data" ||
		(receipt.Status != "active" && receipt.Status != "dry-run") {
		return fmt.Errorf("creator import receipt contract is invalid")
	}
	actual := make(map[string]bool, len(receipt.AuthorIDs))
	for _, authorID := range receipt.AuthorIDs {
		if strings.TrimSpace(authorID) == "" || actual[authorID] {
			return fmt.Errorf("creator import receipt authorIds are invalid")
		}
		actual[authorID] = true
	}
	if len(actual) != len(expectedAuthors) {
		return fmt.Errorf("creator import receipt author closure mismatch")
	}
	for authorID := range expectedAuthors {
		if !actual[authorID] {
			return fmt.Errorf("creator import receipt missing authorId %s", authorID)
		}
	}
	return nil
}

func ValidatePostAuthors(posts []PostDoc, authors map[string]bool) error {
	for _, post := range posts {
		if strings.TrimSpace(post.AuthorID) == "" || !authors[post.AuthorID] {
			return fmt.Errorf("%s: post author is not imported by the release creator closure", post.PostRef)
		}
	}
	return nil
}

func ToSet(items []string) map[string]bool {
	s := make(map[string]bool, len(items))
	for _, it := range items {
		s[it] = true
	}
	return s
}

func missingDesiredRefs(filter map[string]bool, loadedRefs []string) []string {
	if filter == nil || len(filter) == 0 {
		return nil
	}
	loaded := make(map[string]bool, len(loadedRefs))
	for _, ref := range loadedRefs {
		loaded[ref] = true
	}
	missing := make([]string, 0)
	for ref := range filter {
		if !loaded[ref] {
			missing = append(missing, ref)
		}
	}
	sort.Strings(missing)
	return missing
}

type postManifest struct {
	ContentType           string                   `json:"contentType"`
	Title                 string                   `json:"title"`
	Caption               string                   `json:"caption"`
	DisplayTitle          string                   `json:"displayTitle"`
	Body                  string                   `json:"body"`
	EntityRefs            []string                 `json:"entityRefs"`
	NormalizedEntityRefs  []string                 `json:"normalizedEntityRefs"`
	TagRefs               []string                 `json:"tagRefs"`
	IntersectionHints     []IntersectionHintDoc    `json:"intersectionHints"`
	SemanticMentions      any                      `json:"semanticMentions"`
	AuthorID              string                   `json:"authorId"`
	CreatorProfileID      string                   `json:"creatorProfileId"`
	CreatorArchetype      string                   `json:"creatorArchetype"`
	CreatorProfileVersion string                   `json:"creatorProfileVersion"`
	CreatorDisclosure     map[string]any           `json:"creatorDisclosure"`
	ExperienceClaimMode   string                   `json:"experienceClaimMode"`
	AuthorQualitySignals  map[string]any           `json:"authorQualitySignals"`
	Assets                []AssetManifestItem      `json:"assets"`
	SourceCollectionID    string                   `json:"sourceCollectionId"`
	SourcePlatform        string                   `json:"sourcePlatform"`
	Creator               any                      `json:"creator"`
	Page                  any                      `json:"page"`
	LicenseProof          any                      `json:"licenseProof"`
	SourceCreator         string                   `json:"sourceCreator"`
	SourceCollectionURL   string                   `json:"sourceCollectionUrl"`
	LicenseProofRef       string                   `json:"licenseProofRef"`
	Template              string                   `json:"template"`
	GeneratorModel        string                   `json:"generatorModel"`
	ArticleDigest         string                   `json:"articleMarkdownDigest"`
	PublishTitle          string                   `json:"publishTitle"`
	PublishAngle          string                   `json:"publishAngle"`
	PublishSeq            int                      `json:"publishSeq"`
	SourceTaskId          string                   `json:"sourceTaskId"`
	ArticleAssetManifest  *ArticleAssetManifestDoc `json:"articleAssetManifest"`
	CreatedAt             string                   `json:"createdAt"`
	UpdatedAt             string                   `json:"updatedAt"`
	PublishedAt           string                   `json:"publishedAt"`
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
	if !casObjectKeyPattern.MatchString(strings.TrimSpace(asset.ObjectKey)) {
		return fmt.Errorf("%s: asset manifest objectKey must be CAS path", ref)
	}
	if !sha256Pattern.MatchString(strings.TrimSpace(asset.Sha256)) {
		return fmt.Errorf("%s: asset manifest sha256 invalid", ref)
	}
	if asset.SourceOriginalSha256 != "" && !sha256Pattern.MatchString(strings.TrimSpace(asset.SourceOriginalSha256)) {
		return fmt.Errorf("%s: asset manifest sourceOriginalSha256 invalid", ref)
	}
	return nil
}

func parseRightsAuditStatus(raw string) (RightsAuditStatus, error) {
	status := RightsAuditStatus(strings.TrimSpace(raw))
	switch status {
	case RightsAuditStatusVerified, RightsAuditStatusUnverified:
		return status, nil
	default:
		return "", fmt.Errorf("rightsAuditStatus must be verified or unverified")
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

func validateImageAssets(assets []AssetManifestItem, sourceCollectionID string, ref string) error {
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
		case RightsAuditStatusUnverified:
			if !hasNonEmptyString(asset.RightsAuditIssues) {
				return fmt.Errorf("%s: unverified image asset %q missing audit issues", ref, asset.AssetID)
			}
		}
	}
	return nil
}

func validateVideoAssets(assets []AssetManifestItem, ref string) error {
	byID := make(map[string]AssetManifestItem, len(assets))
	for _, asset := range assets {
		if err := validateAssetItem(asset, ref); err != nil {
			return err
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

func BindPostAssetURLs(posts []PostDoc, mediaBaseURL string) error {
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
	base := strings.TrimRight(strings.TrimSpace(mediaBaseURL), "/")
	parsed, err := url.Parse(base)
	if err != nil ||
		(parsed.Scheme != "http" && parsed.Scheme != "https") ||
		parsed.Host == "" ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" {
		return fmt.Errorf("media base URL must be an absolute http(s) URL")
	}
	for postIndex := range posts {
		assets := posts[postIndex].Assets
		byID := make(map[string]*AssetManifestItem, len(assets))
		for assetIndex := range assets {
			asset := &assets[assetIndex]
			asset.CDNURL = base + "/" + strings.TrimLeft(asset.ObjectKey, "/")
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
		return fmt.Errorf("%s: system creator manifest missing creatorProfileVersion", ref)
	}
	if strings.TrimSpace(m.ExperienceClaimMode) == "" {
		return fmt.Errorf("%s: system creator manifest missing experienceClaimMode", ref)
	}
	if m.CreatorDisclosure == nil {
		return fmt.Errorf("%s: system creator manifest missing creatorDisclosure", ref)
	}
	if m.CreatorDisclosure["type"] != "platform_virtual_creator" {
		return fmt.Errorf("%s: creatorDisclosure.type must be platform_virtual_creator", ref)
	}
	if m.CreatorDisclosure["visible"] != true {
		return fmt.Errorf("%s: creatorDisclosure.visible must be true", ref)
	}
	if strings.TrimSpace(fmt.Sprint(m.CreatorDisclosure["displayText"])) == "" {
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

// LoadPosts 从对象闭包的 posts/ 加载内容；filter 使用相对 posts/ 的对象引用。
func LoadPosts(publishRoot string, filter map[string]bool) ([]PostDoc, error) {
	postsRoot := filepath.Join(publishRoot, "posts")
	var docs []PostDoc
	var loadedObjectRefs []string
	err := filepath.WalkDir(postsRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "manifest.json" {
			return nil
		}
		rel, rerr := filepath.Rel(postsRoot, filepath.Dir(path))
		if rerr != nil {
			return rerr
		}
		objectRef := filepath.ToSlash(rel)
		if filter != nil && !filter[objectRef] {
			return nil
		}
		postRef := filepath.ToSlash(filepath.Join("posts", rel))
		raw, rerr := os.ReadFile(path)
		if rerr != nil {
			return rerr
		}
		var m postManifest
		if jerr := json.Unmarshal(raw, &m); jerr != nil {
			return jerr
		}
		if err := validateCreatorProjection(m, postRef); err != nil {
			return err
		}
		if err := ValidateArticleAssetManifest(m.ArticleAssetManifest, postRef); err != nil {
			return err
		}
		if strings.EqualFold(strings.TrimSpace(m.ContentType), "image") {
			if err := validateImageAssets(m.Assets, m.SourceCollectionID, postRef); err != nil {
				return err
			}
		}
		if strings.EqualFold(strings.TrimSpace(m.ContentType), "video") {
			if len(m.Assets) == 0 || len(m.Assets) > 20 {
				return fmt.Errorf("%s: video manifest assets must contain 1..20 items", postRef)
			}
			if err := validateVideoAssets(m.Assets, postRef); err != nil {
				return err
			}
		}
		if err := postsemantic.ValidateSuppliedRefs(
			m.SemanticMentions,
			m.EntityRefs,
			m.TagRefs,
		); err != nil {
			return fmt.Errorf("%s: %w", postRef, err)
		}
		article := ""
		if a, aerr := os.ReadFile(filepath.Join(filepath.Dir(path), "article.md")); aerr == nil {
			article = string(a)
		}
		segs := strings.Split(postRef, "/")
		title, angle := m.PublishTitle, m.PublishAngle
		if strings.EqualFold(strings.TrimSpace(m.ContentType), "image") {
			title = m.Title
			if title == "" && m.DisplayTitle != "" {
				title = m.DisplayTitle
			}
		}
		if len(segs) >= 4 {
			if angle == "" {
				angle = segs[2]
			}
			if title == "" && !strings.EqualFold(strings.TrimSpace(m.ContentType), "image") {
				title = segs[3]
			}
		}
		publishedAt, err := parseManifestTime(postRef, "publishedAt", m.PublishedAt)
		if err != nil {
			return err
		}
		createdAt, err := parseOptionalManifestTime(postRef, "createdAt", m.CreatedAt, publishedAt)
		if err != nil {
			return err
		}
		updatedAt, err := parseOptionalManifestTime(postRef, "updatedAt", m.UpdatedAt, publishedAt)
		if err != nil {
			return err
		}
		rawEntityRefs := append([]string(nil), m.EntityRefs...)
		normalizedEntityRefs := firstNonEmptyRefs(m.NormalizedEntityRefs, m.EntityRefs)
		activeTagRefs := append([]string(nil), m.TagRefs...)
		if postsemantic.Present(m.SemanticMentions) {
			projection := postsemantic.Project(m.SemanticMentions)
			if len(rawEntityRefs) == 0 {
				rawEntityRefs = projection.EntityRefs
			}
			normalizedEntityRefs = firstNonEmptyRefs(m.NormalizedEntityRefs, projection.EntityRefs)
			if len(activeTagRefs) == 0 {
				activeTagRefs = projection.TagRefs
			}
		}
		if err := validateIntersectionHints(m.IntersectionHints, normalizedEntityRefs, activeTagRefs, postRef); err != nil {
			return err
		}
		body := m.Body
		if strings.EqualFold(strings.TrimSpace(m.ContentType), "image") {
			body = m.Caption
			if body == "" {
				body = m.Body
			}
		}
		assets := m.Assets
		if len(assets) == 0 && m.ArticleAssetManifest != nil {
			assets = m.ArticleAssetManifest.Assets
		}
		docs = append(docs, PostDoc{
			PostRef:               postRef,
			ContentType:           m.ContentType,
			Title:                 title,
			Body:                  body,
			Angle:                 angle,
			Seq:                   m.PublishSeq,
			EntityRefs:            rawEntityRefs,
			NormalizedEntityRefs:  normalizedEntityRefs,
			TagRefs:               activeTagRefs,
			IntersectionHints:     append([]IntersectionHintDoc(nil), m.IntersectionHints...),
			SemanticMentions:      m.SemanticMentions,
			AuthorID:              m.AuthorID,
			CreatorProfileID:      m.CreatorProfileID,
			CreatorArchetype:      m.CreatorArchetype,
			CreatorProfileVersion: m.CreatorProfileVersion,
			CreatorDisclosure:     m.CreatorDisclosure,
			ExperienceClaimMode:   m.ExperienceClaimMode,
			AuthorQualitySignals:  m.AuthorQualitySignals,
			Assets:                assets,
			SourceCollectionID:    m.SourceCollectionID,
			SourcePlatform:        m.SourcePlatform,
			Creator:               firstSourceFact(m.Creator, m.SourceCreator),
			Page:                  firstSourceFact(m.Page, m.SourceCollectionURL),
			LicenseProof:          firstSourceFact(m.LicenseProof, m.LicenseProofRef),
			Template:              m.Template,
			GeneratorModel:        m.GeneratorModel,
			ArticleMarkdown:       article,
			ArticleDigest:         m.ArticleDigest,
			ArticleAssetManifest:  m.ArticleAssetManifest,
			SourceTaskId:          m.SourceTaskId,
			CreatedAt:             createdAt,
			UpdatedAt:             updatedAt,
			PublishedAt:           publishedAt,
		})
		loadedObjectRefs = append(loadedObjectRefs, objectRef)
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	if missing := missingDesiredRefs(filter, loadedObjectRefs); len(missing) > 0 {
		return nil, fmt.Errorf(
			"desired posts missing from canonical publish: %s",
			strings.Join(missing, ", "),
		)
	}
	return docs, nil
}

func firstSourceFact(values ...any) any {
	for _, value := range values {
		if sourceFactPresent(value) {
			return value
		}
	}
	return nil
}

func sourceFactPresent(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case string:
		return strings.TrimSpace(typed) != ""
	case map[string]any:
		return len(typed) > 0
	default:
		return true
	}
}

func firstNonEmptyRefs(preferred, fallback []string) []string {
	if len(preferred) > 0 {
		return append([]string(nil), preferred...)
	}
	return append([]string(nil), fallback...)
}

type entityFile struct {
	Label            string         `json:"label"`
	Domain           string         `json:"domain"`
	Type             string         `json:"type"`
	TagRefs          []string       `json:"tagRefs"`
	ConditionProfile map[string]any `json:"conditionProfile"`
	SourceTaskId     string         `json:"sourceTaskId"`
}

// LoadEntities 从 publish/entities 加载实体；filter 非空时只保留其中的 entityRef。
func LoadEntities(publishRoot string, filter map[string]bool) ([]EntityDoc, error) {
	entRoot := filepath.Join(publishRoot, "entities")
	var docs []EntityDoc
	err := filepath.WalkDir(entRoot, func(path string, d os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || d.Name() != "_entity.json" {
			return nil
		}
		rel, rerr := filepath.Rel(entRoot, filepath.Dir(path))
		if rerr != nil {
			return rerr
		}
		entityRef := filepath.ToSlash(rel)
		if filter != nil && !filter[entityRef] {
			return nil
		}
		raw, rerr := os.ReadFile(path)
		if rerr != nil {
			return rerr
		}
		var ef entityFile
		if jerr := json.Unmarshal(raw, &ef); jerr != nil {
			return jerr
		}
		segs := strings.Split(entityRef, "/")
		domain, etype, name := ef.Domain, ef.Type, ""
		if len(segs) >= 3 {
			if domain == "" {
				domain = segs[0]
			}
			if etype == "" {
				etype = segs[1]
			}
			name = segs[len(segs)-1]
		}
		page := ""
		hasPage := false
		if p, perr := os.ReadFile(filepath.Join(filepath.Dir(path), "page.md")); perr == nil {
			page = string(p)
			hasPage = true
		}
		assetManifest := (*EntityAssetManifestDoc)(nil)
		assetRefsPath := filepath.Join(filepath.Dir(path), "asset.refs.json")
		if rawManifest, merr := os.ReadFile(assetRefsPath); merr == nil {
			var parsed EntityAssetManifestDoc
			if jerr := json.Unmarshal(rawManifest, &parsed); jerr != nil {
				return jerr
			}
			if err := validateEntityAssetManifest(&parsed, entityRef); err != nil {
				return err
			}
			assetManifest = &parsed
		} else if !os.IsNotExist(merr) {
			return merr
		}
		label := ef.Label
		if label == "" {
			label = name
		}
		docs = append(docs, EntityDoc{
			EntityRef:        entityRef,
			Domain:           domain,
			Etype:            etype,
			Name:             name,
			Label:            label,
			TagRefs:          ef.TagRefs,
			Page:             page,
			HasPage:          hasPage,
			AssetManifest:    assetManifest,
			ConditionProfile: ef.ConditionProfile,
			SourceTaskId:     ef.SourceTaskId,
		})
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return docs, err
	}
	loadedRefs := make([]string, 0, len(docs))
	for _, doc := range docs {
		loadedRefs = append(loadedRefs, doc.EntityRef)
	}
	if missing := missingDesiredRefs(filter, loadedRefs); len(missing) > 0 {
		return nil, fmt.Errorf(
			"desired entities missing from canonical publish: %s",
			strings.Join(missing, ", "),
		)
	}
	return docs, nil
}
