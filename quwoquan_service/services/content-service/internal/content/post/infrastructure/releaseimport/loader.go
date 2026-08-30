// Package releaseimport implements the pure immutable-release loading layer.
//
// 唯一内容真相源是自治 canonical object package；选择集只来自 immutable release
// payload/desired_state.json。禁止 sample bundle fallback 或无 release 的全树导入。
package releaseimport

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

const ArticleAssetManifestSchema = "article-asset-manifest"

type RightsAuditStatus string

const (
	RightsAuditStatusVerified   RightsAuditStatus = "verified"
	RightsAuditStatusUnverified RightsAuditStatus = "unverified"
)

var sha256Pattern = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type AssetManifestItem struct {
	AssetID string `json:"assetId" bson:"assetId"`
	Kind    string `json:"kind,omitempty" bson:"kind,omitempty"`
	// AccessMode 是媒体交付访问模式（DEC-033，契约 PostArticleAsset.accessMode，
	// enum 唯一真相源 contracts/metadata/_shared/types.yaml
	// MediaDeliveryAccessMode）。由 release header 的 releaseClass 单点映射写入，
	// signed_grant 时 App 必须按 assetId 换取短签。新 immutable release 必须
	// 显式 public|signed_grant；空串只属于具名 legacy-public migration 边界，
	// 不得进入本 importer。
	AccessMode           string   `json:"accessMode,omitempty" bson:"accessMode,omitempty"`
	ObjectKey            string   `json:"objectKey,omitempty" bson:"-"`
	Version              int64    `json:"version,omitempty" bson:"version,omitempty"`
	PublicSliceKey       string   `json:"publicSliceKey,omitempty" bson:"publicSliceKey,omitempty"`
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
	PostRef              string                          `json:"postRef" bson:"postRef"`
	ContentID            string                          `json:"contentId" bson:"contentId"`
	ContentVersion       int64                           `json:"contentVersion" bson:"contentVersion"`
	PoolSourceType       string                          `json:"poolSourceType" bson:"poolSourceType"`
	VariantPurpose       string                          `json:"variantPurpose" bson:"variantPurpose"`
	Admission            ContentAdmission                `json:"admission" bson:"admission"`
	PoolStatus           string                          `json:"poolStatus" bson:"poolStatus"`
	ContentType          string                          `json:"contentType" bson:"contentType"`
	ContentIdentity      string                          `json:"contentIdentity" bson:"contentIdentity"`
	Title                string                          `json:"title" bson:"title"`
	Body                 string                          `json:"body" bson:"body"`
	Angle                string                          `json:"angle" bson:"angle"`
	Seq                  int                             `json:"seq" bson:"seq"`
	EntityRefs           []string                        `json:"entityRefs" bson:"entityRefs"`
	NormalizedEntityRefs []string                        `json:"normalizedEntityRefs" bson:"normalizedEntityRefs"`
	TagRefs              []string                        `json:"tagRefs" bson:"tagRefs"`
	IntersectionHints    []IntersectionHintDoc           `json:"intersectionHints" bson:"intersectionHints"`
	SemanticMentions     []postmodel.PostSemanticMention `json:"semanticMentions" bson:"semanticMentions"`
	AuthorID             string                          `json:"authorId" bson:"authorId"`
	AuthorDisplayName    string                          `json:"authorDisplayNameSnapshot" bson:"authorDisplayNameSnapshot"`
	AuthorAvatarURL      string                          `json:"authorAvatarUrlSnapshot" bson:"authorAvatarUrlSnapshot"`
	// AuthorAvatarAssetID 作者头像的媒体资产标识（DEC-033），来源是 release
	// creator profile 的 avatarAsset.assetId；头像缺席时为空串（落库时写 null）。
	AuthorAvatarAssetID   string                             `json:"authorAvatarAssetId" bson:"authorAvatarAssetId"`
	CreatorProfileID      string                             `json:"creatorProfileId" bson:"creatorProfileId"`
	CreatorArchetype      string                             `json:"creatorArchetype" bson:"creatorArchetype"`
	CreatorProfileVersion string                             `json:"creatorProfileVersion" bson:"creatorProfileVersion"`
	CreatorDisclosure     postmodel.PostCreatorDisclosure    `json:"creatorDisclosure" bson:"creatorDisclosure"`
	ExperienceClaimMode   string                             `json:"experienceClaimMode" bson:"experienceClaimMode"`
	AuthorQualitySignals  postmodel.PostAuthorQualitySignals `json:"authorQualitySignals" bson:"authorQualitySignals"`
	Assets                []AssetManifestItem                `json:"assets" bson:"assets"`
	SourceCollectionID    string                             `json:"sourceCollectionId" bson:"sourceCollectionId"`
	SourcePlatform        string                             `json:"sourcePlatform" bson:"sourcePlatform"`
	SourceAttribution     postmodel.SourceAttribution        `json:"sourceAttribution,omitempty" bson:"sourceAttribution,omitempty"`
	Creator               any                                `json:"creator" bson:"creator"`
	Page                  any                                `json:"page" bson:"page"`
	LicenseProof          any                                `json:"licenseProof" bson:"licenseProof"`
	Template              string                             `json:"template" bson:"template"`
	ArticleMarkdown       string                             `json:"articleMarkdown" bson:"articleMarkdown"`
	ArticleDigest         string                             `json:"articleDigest" bson:"articleDigest"`
	ArticleAssetManifest  *ArticleAssetManifestDoc           `json:"articleAssetManifest" bson:"articleAssetManifest"`
	CreatedAt             time.Time                          `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time                          `json:"updatedAt" bson:"updatedAt"`
	PublishedAt           time.Time                          `json:"publishedAt" bson:"publishedAt"`
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

// ReleaseBinding is the immutable identity shared by the canonical release
// header and its attestation. ManifestDigest is the attested digest of the
// complete payload, not a digest derived from a mutable environment report.
type ReleaseBinding struct {
	ReleaseID      string
	SourceOwner    string
	ReleaseKind    string
	ReleaseClass   string
	ManifestDigest string
}

func LoadReleaseBinding(releaseRoot string) (ReleaseBinding, error) {
	empty := ReleaseBinding{}
	headerPath := filepath.Join(releaseRoot, "payload", "release.json")
	attestationPath := filepath.Join(releaseRoot, "attestations", "release.json")
	var header struct {
		Schema       string `json:"schema"`
		ReleaseID    string `json:"releaseId"`
		SourceOwner  string `json:"sourceOwner"`
		ReleaseKind  string `json:"releaseKind"`
		ReleaseClass string `json:"releaseClass"`
	}
	if err := loadReleaseJSON(headerPath, &header); err != nil {
		return empty, fmt.Errorf("load release header: %w", err)
	}
	var attestation struct {
		Schema        string `json:"schema"`
		ReleaseID     string `json:"releaseId"`
		SourceOwner   string `json:"sourceOwner"`
		ReleaseKind   string `json:"releaseKind"`
		PayloadSHA256 string `json:"payloadSha256"`
	}
	if err := loadReleaseJSON(attestationPath, &attestation); err != nil {
		return empty, fmt.Errorf("load release attestation: %w", err)
	}
	for path, values := range map[string][2]string{
		headerPath + ":schema":           {header.Schema, "quwoquan_data.release"},
		headerPath + ":sourceOwner":      {header.SourceOwner, "qwq_data"},
		attestationPath + ":schema":      {attestation.Schema, "quwoquan_data.release_attestation"},
		attestationPath + ":sourceOwner": {attestation.SourceOwner, "qwq_data"},
	} {
		if strings.TrimSpace(values[0]) != values[1] {
			return empty, fmt.Errorf("%s must be %q", path, values[1])
		}
	}
	headerReleaseKind := strings.TrimSpace(header.ReleaseKind)
	attestedReleaseKind := strings.TrimSpace(attestation.ReleaseKind)
	if !isFullSyncReleaseKind(headerReleaseKind) {
		return empty, fmt.Errorf(
			"%s:releaseKind must be %q or %q",
			headerPath,
			"content",
			"empty_baseline",
		)
	}
	if headerReleaseKind != attestedReleaseKind {
		return empty, fmt.Errorf(
			"release header/attestation releaseKind drift: header=%q attestation=%q",
			headerReleaseKind,
			attestedReleaseKind,
		)
	}
	headerReleaseID := strings.TrimSpace(header.ReleaseID)
	attestedReleaseID := strings.TrimSpace(attestation.ReleaseID)
	if headerReleaseID == "" || headerReleaseID != attestedReleaseID {
		return empty, fmt.Errorf(
			"release header/attestation releaseId drift: header=%q attestation=%q",
			headerReleaseID,
			attestedReleaseID,
		)
	}
	manifestDigest := strings.TrimSpace(attestation.PayloadSHA256)
	if !sha256Pattern.MatchString(manifestDigest) {
		return empty, fmt.Errorf(
			"%s: payloadSha256 must use canonical sha256:<64 lowercase hex>",
			attestationPath,
		)
	}
	return ReleaseBinding{
		ReleaseID:      headerReleaseID,
		SourceOwner:    "qwq_data",
		ReleaseKind:    headerReleaseKind,
		ReleaseClass:   strings.TrimSpace(header.ReleaseClass),
		ManifestDigest: manifestDigest,
	}, nil
}

func isFullSyncReleaseKind(kind string) bool {
	switch kind {
	case "content", "empty_baseline":
		return true
	default:
		return false
	}
}

func loadReleaseJSON(path string, target any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(raw, target); err != nil {
		return fmt.Errorf("decode %s: %w", path, err)
	}
	return nil
}

type creatorProfileDoc struct {
	Schema      string                `json:"schema"`
	CreatorID   string                `json:"creatorId"`
	UserID      string                `json:"userId"`
	AuthorID    string                `json:"authorId"`
	DisplayName string                `json:"displayName"`
	AvatarAsset *creatorMediaAssetRef `json:"avatarAsset"`
}

type creatorMediaAssetRef struct {
	AssetID string `json:"assetId"`
	Kind    string `json:"kind"`
	SHA256  string `json:"sha256"`
}

// CreatorAuthorSnapshot is the immutable creator profile projection used by
// imported Posts. It keeps the public author identity bound to the same
// release object closure as authorId instead of asking the App to invent a
// fallback display name or avatar.
type CreatorAuthorSnapshot struct {
	AuthorID    string
	DisplayName string
	AvatarURL   string
	// AvatarAssetID 头像的媒体资产标识（creator profile avatarAsset.assetId）；
	// 无头像时为空串，表示缺席。
	AvatarAssetID string
}

type creatorImportReceipt struct {
	Schema      string   `json:"schema"`
	Status      string   `json:"status"`
	ReleaseID   string   `json:"releaseId"`
	SourceOwner string   `json:"sourceOwner"`
	AuthorIDs   []string `json:"authorIds"`
}

type ReleaseMediaAsset = runtimemedia.ReleaseMediaAsset

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

func LoadReleaseMediaAssets(releaseRoot, expectedReleaseID, releaseClass string) (map[string]ReleaseMediaAsset, error) {
	return runtimemedia.LoadReleaseMediaAssets(releaseRoot, expectedReleaseID, releaseClass)
}

// LoadCreatorAuthorSnapshots makes the release's public-author closure,
// display name, and optional avatar explicit for content import. A Post can
// never be materialized before its canonical creator profile has been imported
// by user-service and projected into the Post snapshot fields.
func LoadCreatorAuthorSnapshots(
	objectRoot string,
	filter map[string]bool,
	releaseAssets map[string]ReleaseMediaAsset,
	mediaAvatarBaseURL string,
) (map[string]CreatorAuthorSnapshot, error) {
	authors := make(map[string]CreatorAuthorSnapshot, len(filter))
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
		profile.DisplayName = strings.TrimSpace(profile.DisplayName)
		if profile.Schema != "quwoquan_data.creator_profile" || profile.CreatorID != ref ||
			strings.TrimSpace(profile.AuthorID) == "" || profile.UserID != profile.AuthorID ||
			profile.DisplayName == "" {
			return nil, fmt.Errorf("creator profile invalid: %s", ref)
		}
		if _, exists := authors[profile.AuthorID]; exists {
			return nil, fmt.Errorf("creator authorId is duplicated: %s", profile.AuthorID)
		}
		avatarURL := ""
		avatarAssetID := ""
		if profile.AvatarAsset != nil {
			resolved, err := runtimemedia.ResolveReleaseMediaAsset(
				releaseAssets,
				runtimemedia.MediaDeliveryBases{Avatar: mediaAvatarBaseURL},
				profile.AvatarAsset.AssetID,
				profile.AvatarAsset.Kind,
				profile.AvatarAsset.SHA256,
				"creators/"+ref,
			)
			if err != nil {
				return nil, fmt.Errorf("creator %s avatar differs from release media authority: %w", ref, err)
			}
			avatarURL = resolved.DeliveryRef
			avatarAssetID = strings.TrimSpace(profile.AvatarAsset.AssetID)
		}
		authors[profile.AuthorID] = CreatorAuthorSnapshot{
			AuthorID:      profile.AuthorID,
			DisplayName:   profile.DisplayName,
			AvatarURL:     avatarURL,
			AvatarAssetID: avatarAssetID,
		}
	}
	return authors, nil
}

func CreatorAuthorIDs(snapshots map[string]CreatorAuthorSnapshot) map[string]bool {
	authors := make(map[string]bool, len(snapshots))
	for authorID := range snapshots {
		authors[authorID] = true
	}
	return authors
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

// LoadPosts 从对象闭包的 posts/ 加载内容；filter 使用相对 posts/ 的对象引用。
// LoadPosts 校验并装载 release 对象闭包内的 post 文档。releaseClass 是 release
// header 声明的发布类别（"research"/"commercial"）；空值只保留给 pre-pool
// fixture 的 rights 校验。新 release 的媒体交付判据在 Bind +
// ValidateImportedPostMediaBindings 边界显式收敛。
func LoadPosts(publishRoot string, filter map[string]bool, releaseClass string) ([]PostDoc, error) {
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
		if err := normalizeImportedContentPoolRecord(&m, postRef); err != nil {
			return err
		}
		_ = resolveCreatorProfileVersion(&m)
		if err := validateCreatorProjection(m, postRef); err != nil {
			return err
		}
		if err := ValidateArticleAssetManifest(m.ArticleAssetManifest, postRef); err != nil {
			return err
		}
		if strings.EqualFold(strings.TrimSpace(m.ContentType), "image") {
			if err := validateImageAssets(m.Assets, m.SourceCollectionID, postRef, releaseClass); err != nil {
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
		contentIdentity, err := canonicalImportedContentIdentity(m.ContentIdentity)
		if err != nil {
			return fmt.Errorf("%s: %w", postRef, err)
		}
		docs = append(docs, PostDoc{
			PostRef:               postRef,
			ContentID:             m.ContentID,
			ContentVersion:        m.Version,
			PoolSourceType:        m.PoolSourceType,
			VariantPurpose:        m.VariantPurpose,
			Admission:             m.Admission,
			PoolStatus:            m.PoolStatus,
			ContentType:           m.ContentType,
			ContentIdentity:       contentIdentity,
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
			SourceAttribution:     m.SourceAttribution,
			Creator:               firstSourceFact(m.Creator, m.SourceCreator),
			Page:                  firstSourceFact(m.Page, m.SourceCollectionURL),
			LicenseProof:          firstSourceFact(m.LicenseProof, m.LicenseProofRef),
			Template:              m.Template,
			ArticleMarkdown:       article,
			ArticleDigest:         m.ArticleDigest,
			ArticleAssetManifest:  m.ArticleAssetManifest,
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
