package graphql

import (
	"errors"
	"fmt"
	"strings"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

var supportedContentTypes = map[string]struct{}{
	"article": {}, "image": {}, "micro": {}, "video": {},
}

type contentPostDetailBase struct {
	PostID                  string             `json:"postId"`
	ContentType             string             `json:"contentType"`
	ContentIdentity         *string            `json:"contentIdentity"`
	AssistantUsePolicy      *string            `json:"assistantUsePolicy"`
	AuthorID                *string            `json:"authorId"`
	AuthorDisplayName       *string            `json:"authorDisplayName"`
	AuthorAvatarURL         *string            `json:"authorAvatarUrl"`
	Title                   *string            `json:"title"`
	Body                    *string            `json:"body"`
	Summary                 *string            `json:"summary"`
	CoverURL                *string            `json:"coverUrl"`
	SourceAttribution       *sourceAttribution `json:"sourceAttribution"`
	Location                *geoPoint          `json:"location"`
	LocationName            *string            `json:"locationName"`
	GeoTagRef               *string            `json:"geoTagRef"`
	VisitedAt               *string            `json:"visitedAt"`
	PrimaryHomepageID       *string            `json:"primaryHomepageId"`
	CanonicalEntityID       *string            `json:"canonicalEntityId"`
	PrimaryHomepageType     *string            `json:"primaryHomepageType"`
	PrimaryHomepageSnapshot *homepageSnapshot  `json:"primaryHomepageSnapshot"`
	Status                  string             `json:"status"`
	Visibility              string             `json:"visibility"`
	GatheringRef            *string            `json:"gatheringRef"`
	LikeCount               int64              `json:"likeCount"`
	CommentCount            int64              `json:"commentCount"`
	ShareCount              int64              `json:"shareCount"`
	ViewCount               int64              `json:"viewCount"`
	// viewerLiked 在 owner 内部 persisted 读链路恒为 null：API Edge 以 service
	// 身份调用，本传输不承载 viewer 维度；true/false 只能来自认证 REST 读。
	ViewerLiked *bool   `json:"viewerLiked"`
	CreatedAt   string  `json:"createdAt"`
	UpdatedAt   string  `json:"updatedAt"`
	PublishedAt *string `json:"publishedAt"`
}

type sourceAttribution struct {
	IsOriginal                    bool    `json:"isOriginal"`
	OriginalCreatorID             *string `json:"originalCreatorId"`
	OriginalCreatorName           string  `json:"originalCreatorName"`
	OriginalCreatorProfileURL     *string `json:"originalCreatorProfileUrl"`
	Platform                      string  `json:"platform"`
	SourcePostURL                 string  `json:"sourcePostUrl"`
	OriginalAssetURL              string  `json:"originalAssetUrl"`
	AttributionText               string  `json:"attributionText"`
	RightsBasis                   string  `json:"rightsBasis"`
	CommercialAuthorizationStatus string  `json:"commercialAuthorizationStatus"`
	PublicationAdmission          string  `json:"publicationAdmission"`
	AuthorizationProofURL         *string `json:"authorizationProofUrl"`
	TermsURL                      *string `json:"termsUrl"`
	RiskAcceptanceID              *string `json:"riskAcceptanceId"`
	WatermarkStatus               string  `json:"watermarkStatus"`
	AudioRightsStatus             string  `json:"audioRightsStatus"`
	ModelReleaseStatus            string  `json:"modelReleaseStatus"`
	PropertyReleaseStatus         string  `json:"propertyReleaseStatus"`
	CollectedAt                   string  `json:"collectedAt"`
	TakedownPolicy                string  `json:"takedownPolicy"`
}

type geoPoint struct {
	Latitude  float64 `json:"latitude"`
	Longitude float64 `json:"longitude"`
}
type homepageSnapshot struct {
	CanonicalEntityID *string `json:"canonicalEntityId"`
	Title             *string `json:"title"`
	Subtitle          *string `json:"subtitle"`
	CoverURL          *string `json:"coverUrl"`
}

func projectContentPostDetailBase(detail postports.PostDetailSlice) (any, error) {
	postID, contentType, err := requiredIdentity(detail)
	if err != nil {
		return nil, err
	}
	status, err := requiredString(string(detail.Status), "status")
	if err != nil {
		return nil, err
	}
	visibility, err := requiredString(string(detail.Visibility), "visibility")
	if err != nil {
		return nil, err
	}
	if detail.CreatedAt.IsZero() || detail.UpdatedAt.IsZero() {
		return nil, errors.New("content post base slice is missing lifecycle timestamps")
	}
	if detail.LikeCount < 0 || detail.CommentCount < 0 || detail.ShareCount < 0 || detail.ViewCount < 0 {
		return nil, errors.New("content post base slice contains a negative counter")
	}
	attribution, err := projectAttribution(detail.SourceAttribution)
	if err != nil {
		return nil, err
	}
	var location *geoPoint
	if detail.Location != nil {
		location = &geoPoint{Latitude: detail.Location.Latitude, Longitude: detail.Location.Longitude}
	}
	var homepage *homepageSnapshot
	if detail.PrimaryHomepageSnapshot != nil {
		homepage = &homepageSnapshot{
			CanonicalEntityID: nullable(detail.PrimaryHomepageSnapshot.CanonicalEntityID),
			Title:             nullable(detail.PrimaryHomepageSnapshot.Title),
			Subtitle:          nullable(detail.PrimaryHomepageSnapshot.Subtitle),
			CoverURL:          nullable(detail.PrimaryHomepageSnapshot.CoverURL),
		}
	}
	return contentPostDetailBase{
		PostID: postID, ContentType: contentType,
		ContentIdentity:    nullable(string(detail.ContentIdentity)),
		AssistantUsePolicy: nullable(detail.AssistantUsePolicy),
		AuthorID:           nullable(string(detail.AuthorPersonaID)),
		AuthorDisplayName:  nullable(detail.AuthorDisplayName),
		AuthorAvatarURL:    nullable(detail.AuthorAvatarURL),
		Title:              nullable(detail.Title), Body: nullable(detail.Body), Summary: nullable(detail.Summary),
		CoverURL: nullable(detail.CoverURL), SourceAttribution: attribution,
		Location: location, LocationName: nullable(detail.LocationName), GeoTagRef: nullable(detail.GeoTagRef),
		VisitedAt: nullableTime(detail.VisitedAt), PrimaryHomepageID: nullable(detail.PrimaryHomepageID),
		CanonicalEntityID: nullable(detail.CanonicalEntityID), PrimaryHomepageType: nullable(detail.PrimaryHomepageType),
		PrimaryHomepageSnapshot: homepage, Status: status, Visibility: visibility,
		GatheringRef: nullable(detail.GatheringRef),
		LikeCount: detail.LikeCount, CommentCount: detail.CommentCount,
		ShareCount: detail.ShareCount, ViewCount: detail.ViewCount,
		CreatedAt: formatTime(detail.CreatedAt), UpdatedAt: formatTime(detail.UpdatedAt),
		PublishedAt: nullableTime(detail.PublishedAt),
	}, nil
}

func projectAttribution(value *postports.PostSourceAttributionSlice) (*sourceAttribution, error) {
	if value == nil {
		return nil, nil
	}
	required := []struct{ name, value string }{
		{"originalCreatorName", value.OriginalCreatorName}, {"platform", value.Platform},
		{"sourcePostUrl", value.SourcePostURL}, {"originalAssetUrl", value.OriginalAssetURL},
		{"attributionText", value.AttributionText}, {"rightsBasis", value.RightsBasis},
		{"commercialAuthorizationStatus", value.CommercialAuthorizationStatus},
		{"publicationAdmission", value.PublicationAdmission}, {"watermarkStatus", value.WatermarkStatus},
		{"audioRightsStatus", value.AudioRightsStatus}, {"modelReleaseStatus", value.ModelReleaseStatus},
		{"propertyReleaseStatus", value.PropertyReleaseStatus}, {"takedownPolicy", value.TakedownPolicy},
	}
	for _, field := range required {
		if _, err := requiredString(field.value, "sourceAttribution."+field.name); err != nil {
			return nil, err
		}
	}
	if value.CollectedAt.IsZero() {
		return nil, errors.New("sourceAttribution.collectedAt is required")
	}
	return &sourceAttribution{
		IsOriginal: value.IsOriginal, OriginalCreatorID: nullable(value.OriginalCreatorID),
		OriginalCreatorName:       value.OriginalCreatorName,
		OriginalCreatorProfileURL: nullable(value.OriginalCreatorProfileURL), Platform: value.Platform,
		SourcePostURL: value.SourcePostURL, OriginalAssetURL: value.OriginalAssetURL,
		AttributionText: value.AttributionText, RightsBasis: value.RightsBasis,
		CommercialAuthorizationStatus: value.CommercialAuthorizationStatus,
		PublicationAdmission:          value.PublicationAdmission, AuthorizationProofURL: nullable(value.AuthorizationProofURL),
		TermsURL: nullable(value.TermsURL), RiskAcceptanceID: nullable(value.RiskAcceptanceID),
		WatermarkStatus: value.WatermarkStatus, AudioRightsStatus: value.AudioRightsStatus,
		ModelReleaseStatus: value.ModelReleaseStatus, PropertyReleaseStatus: value.PropertyReleaseStatus,
		CollectedAt: formatTime(value.CollectedAt), TakedownPolicy: value.TakedownPolicy,
	}, nil
}

type contentPostDetailSemantic struct {
	PostID           string            `json:"postId"`
	ContentType      string            `json:"contentType"`
	TagRefs          []string          `json:"tagRefs"`
	EntityRefs       []string          `json:"entityRefs"`
	SemanticMentions []semanticMention `json:"semanticMentions"`
}

type semanticMention struct {
	MentionID   string  `json:"mentionId"`
	Kind        string  `json:"kind"`
	Surface     string  `json:"surface"`
	Location    string  `json:"location"`
	RangeStart  *int64  `json:"rangeStart"`
	RangeEnd    *int64  `json:"rangeEnd"`
	Status      string  `json:"status"`
	CandidateID *string `json:"candidateId"`
	TargetRef   *string `json:"targetRef"`
}

func projectContentPostDetailSemantic(detail postports.PostDetailSlice) (any, error) {
	postID, contentType, err := requiredIdentity(detail)
	if err != nil {
		return nil, err
	}
	if len(detail.TagRefs) > maxSemanticRows || len(detail.EntityRefs) > maxSemanticRows || len(detail.SemanticMentions) > maxSemanticRows {
		return nil, errors.New("content post semantic slice exceeds the object-owned 30 item bound")
	}
	mentions := make([]semanticMention, len(detail.SemanticMentions))
	for index, row := range detail.SemanticMentions {
		mentionID, err := requiredString(row.MentionID, fmt.Sprintf("semanticMentions[%d].mentionId", index))
		if err != nil {
			return nil, err
		}
		kind, err := requiredString(row.Kind, fmt.Sprintf("semanticMentions[%d].kind", index))
		if err != nil {
			return nil, err
		}
		surface, err := requiredString(row.Surface, fmt.Sprintf("semanticMentions[%d].surface", index))
		if err != nil {
			return nil, err
		}
		location, err := requiredString(row.Location, fmt.Sprintf("semanticMentions[%d].location", index))
		if err != nil {
			return nil, err
		}
		status, err := requiredString(row.Status, fmt.Sprintf("semanticMentions[%d].status", index))
		if err != nil {
			return nil, err
		}
		var start, end *int64
		if row.RangeStart != 0 || row.RangeEnd != 0 {
			start = int64Pointer(row.RangeStart)
			end = int64Pointer(row.RangeEnd)
		}
		mentions[index] = semanticMention{MentionID: mentionID, Kind: kind, Surface: surface,
			Location: location, RangeStart: start, RangeEnd: end, Status: status,
			CandidateID: nullable(row.CandidateID), TargetRef: nullable(row.TargetRef)}
	}
	return contentPostDetailSemantic{PostID: postID, ContentType: contentType,
		TagRefs: cloneStrings(detail.TagRefs), EntityRefs: cloneStrings(detail.EntityRefs), SemanticMentions: mentions}, nil
}

type contentPostDetailMedia struct {
	PostID           string      `json:"postId"`
	ContentType      string      `json:"contentType"`
	MediaAssetIDs    []string    `json:"mediaAssetIds"`
	MediaURLs        []string    `json:"mediaUrls"`
	MediaItems       []mediaItem `json:"mediaItems"`
	ThumbnailURL     *string     `json:"thumbnailUrl"`
	VideoURL         *string     `json:"videoUrl"`
	Width            *int64      `json:"width"`
	Height           *int64      `json:"height"`
	DurationMS       *int64      `json:"durationMs"`
	CoverStrategy    *string     `json:"coverStrategy"`
	CoverFrameTimeMS *int64      `json:"coverFrameTimeMs"`
}

type mediaItem struct {
	Kind                     string  `json:"kind"`
	MediaAssetID             *string `json:"mediaAssetId"`
	MediaAssetVersion        *int64  `json:"mediaAssetVersion"`
	URL                      string  `json:"url"`
	CoverURL                 *string `json:"coverUrl"`
	DurationMS               *int64  `json:"durationMs"`
	Width                    *int64  `json:"width"`
	Height                   *int64  `json:"height"`
	PreviewTrackManifestURL  *string `json:"previewTrackManifestUrl"`
	PreviewTrackVersion      *int64  `json:"previewTrackVersion"`
	HLSCMAFMasterManifestURL *string `json:"hlsCmafMasterManifestUrl"`
	HLSCMAFDescriptorVersion *int64  `json:"hlsCmafDescriptorVersion"`
	Title                    *string `json:"title"`
}

func projectContentPostDetailMedia(detail postports.PostDetailSlice) (any, error) {
	postID, contentType, err := requiredIdentity(detail)
	if err != nil {
		return nil, err
	}
	if contentType != "image" && contentType != "video" {
		return nil, fmt.Errorf("media slice does not apply to contentType=%s", contentType)
	}
	if len(detail.MediaAssetIDs) > maxMediaRows || len(detail.MediaURLs) > maxMediaRows || len(detail.MediaItems) > maxMediaRows {
		return nil, errors.New("content post media slice exceeds the object-owned 20 item bound")
	}
	items := make([]mediaItem, len(detail.MediaItems))
	for index, row := range detail.MediaItems {
		kind, err := requiredString(row.Kind, fmt.Sprintf("mediaItems[%d].kind", index))
		if err != nil {
			return nil, err
		}
		url, err := requiredString(row.URL, fmt.Sprintf("mediaItems[%d].url", index))
		if err != nil {
			return nil, err
		}
		items[index] = mediaItem{Kind: kind, MediaAssetID: nullable(row.MediaAssetID),
			MediaAssetVersion: positiveInt64(row.MediaAssetVersion), URL: url, CoverURL: nullable(row.CoverURL),
			DurationMS: positiveInt64(row.DurationMS), Width: positiveInt64(row.Width), Height: positiveInt64(row.Height),
			PreviewTrackManifestURL: nullable(row.PreviewTrackManifestURL), PreviewTrackVersion: positiveInt64(row.PreviewTrackVersion),
			HLSCMAFMasterManifestURL: nullable(row.HLSCMAFMasterManifestURL), HLSCMAFDescriptorVersion: positiveInt64(row.HLSCMAFDescriptorVersion),
			Title: nullable(row.Title)}
	}
	return contentPostDetailMedia{PostID: postID, ContentType: contentType,
		MediaAssetIDs: cloneStrings(detail.MediaAssetIDs), MediaURLs: cloneStrings(detail.MediaURLs), MediaItems: items,
		ThumbnailURL: nullable(detail.ThumbnailURL), VideoURL: nullable(detail.VideoURL),
		Width: positiveInt64(detail.Width), Height: positiveInt64(detail.Height), DurationMS: positiveInt64(detail.DurationMS),
		CoverStrategy: nullable(detail.CoverStrategy), CoverFrameTimeMS: positiveInt64(detail.CoverFrameTimeMS)}, nil
}

type contentPostDetailArticleRenderAssets struct {
	PostID                      string                  `json:"postId"`
	ContentType                 string                  `json:"contentType"`
	ArticleMarkdown             *string                 `json:"articleMarkdown"`
	MarkdownDialect             *string                 `json:"markdownDialect"`
	ArticleMarkdownDigest       *string                 `json:"articleMarkdownDigest"`
	ArticleAssetManifestSummary *articleManifestSummary `json:"articleAssetManifestSummary"`
	ArticleAssets               []articleAsset          `json:"articleAssets"`
	ArticleRenderProfileSummary *articleRenderProfile   `json:"articleRenderProfileSummary"`
	ContentVertical             *string                 `json:"contentVertical"`
	ArticleTemplate             *string                 `json:"articleTemplate"`
	ArticleFontPreset           *string                 `json:"articleFontPreset"`
}

type articleManifestSummary struct {
	Schema                string  `json:"schema"`
	MarkdownVersion       *string `json:"markdownVersion"`
	MarkdownDialect       *string `json:"markdownDialect"`
	ArticleMarkdownDigest string  `json:"articleMarkdownDigest"`
	DocumentSHA256        string  `json:"documentSha256"`
	AssetManifestSHA256   string  `json:"assetManifestSha256"`
	DocumentVersionSHA256 string  `json:"documentVersionSha256"`
}
type articleAsset struct {
	AssetID              string  `json:"assetId"`
	Kind                 *string `json:"kind"`
	PublicSliceKey       *string `json:"publicSliceKey"`
	SHA256               *string `json:"sha256"`
	MimeType             *string `json:"mimeType"`
	SourceOriginalSHA256 *string `json:"sourceOriginalSha256"`
	Caption              *string `json:"caption"`
	Role                 *string `json:"role"`
	Width                *int64  `json:"width"`
	Height               *int64  `json:"height"`
	DurationMS           *int64  `json:"durationMs"`
	ThumbnailURL         *string `json:"thumbnailUrl"`
	CoverURL             *string `json:"coverUrl"`
	CoverStrategy        *string `json:"coverStrategy"`
	CoverFrameTimeMS     *int64  `json:"coverFrameTimeMs"`
	SourceCollectionID   *string `json:"sourceCollectionId"`
}
type articleRenderProfile struct {
	Template       *string `json:"template"`
	FontPreset     *string `json:"fontPreset"`
	PaperThemeMode *string `json:"paperThemeMode"`
	PaperTexture   *string `json:"paperTexture"`
}

func projectContentPostDetailArticleRenderAssets(detail postports.PostDetailSlice) (any, error) {
	postID, contentType, err := requiredIdentity(detail)
	if err != nil {
		return nil, err
	}
	if contentType != "article" {
		return nil, fmt.Errorf("article render/assets slice does not apply to contentType=%s", contentType)
	}
	var summary *articleManifestSummary
	assets := make([]articleAsset, 0)
	if detail.ArticleAssetManifest != nil {
		manifest := detail.ArticleAssetManifest
		if len(manifest.Assets) > maxArticleAssetRows {
			return nil, errors.New("article assets exceed the object-owned 20 item bound")
		}
		schema, err := requiredString(manifest.Schema, "articleAssetManifest.schema")
		if err != nil {
			return nil, err
		}
		markdownDigest, err := requiredString(manifest.ArticleMarkdownDigest, "articleAssetManifest.articleMarkdownDigest")
		if err != nil {
			return nil, err
		}
		documentDigest, err := requiredString(manifest.DocumentSHA256, "articleAssetManifest.documentSha256")
		if err != nil {
			return nil, err
		}
		assetDigest, err := requiredString(manifest.AssetManifestSHA256, "articleAssetManifest.assetManifestSha256")
		if err != nil {
			return nil, err
		}
		versionDigest, err := requiredString(manifest.DocumentVersionSHA256, "articleAssetManifest.documentVersionSha256")
		if err != nil {
			return nil, err
		}
		summary = &articleManifestSummary{Schema: schema, MarkdownVersion: nullable(manifest.MarkdownVersion), MarkdownDialect: nullable(manifest.MarkdownDialect),
			ArticleMarkdownDigest: markdownDigest, DocumentSHA256: documentDigest, AssetManifestSHA256: assetDigest, DocumentVersionSHA256: versionDigest}
		assets = make([]articleAsset, len(manifest.Assets))
		for index, row := range manifest.Assets {
			assetID, err := requiredString(row.AssetID, fmt.Sprintf("articleAssets[%d].assetId", index))
			if err != nil {
				return nil, err
			}
			assets[index] = articleAsset{AssetID: assetID, Kind: nullable(row.Kind), PublicSliceKey: nullable(row.PublicSliceKey),
				SHA256: nullable(row.SHA256), MimeType: nullable(row.MimeType), SourceOriginalSHA256: nullable(row.SourceOriginalSHA256),
				Caption: nullable(row.Caption), Role: nullable(row.Role), Width: positiveInt64(row.Width), Height: positiveInt64(row.Height),
				DurationMS: positiveInt64(row.DurationMS), ThumbnailURL: nullable(row.ThumbnailURL), CoverURL: nullable(row.CoverURL),
				CoverStrategy: nullable(row.CoverStrategy), CoverFrameTimeMS: positiveInt64(row.CoverFrameTimeMS), SourceCollectionID: nullable(row.SourceCollectionID)}
		}
	}
	var profile *articleRenderProfile
	if detail.ArticleRenderProfile != nil {
		profile = &articleRenderProfile{Template: nullable(detail.ArticleRenderProfile.Template), FontPreset: nullable(detail.ArticleRenderProfile.FontPreset),
			PaperThemeMode: nullable(detail.ArticleRenderProfile.PaperThemeMode), PaperTexture: nullable(detail.ArticleRenderProfile.PaperTexture)}
	}
	return contentPostDetailArticleRenderAssets{PostID: postID, ContentType: contentType,
		ArticleMarkdown: nullable(detail.ArticleMarkdown), MarkdownDialect: nullable(detail.MarkdownDialect),
		ArticleMarkdownDigest: nullable(detail.ArticleMarkdownDigest), ArticleAssetManifestSummary: summary, ArticleAssets: assets,
		ArticleRenderProfileSummary: profile, ContentVertical: nullable(detail.ContentVertical),
		ArticleTemplate: nullable(detail.ArticleTemplate), ArticleFontPreset: nullable(detail.ArticleFontPreset)}, nil
}

type contentPostDetailArticleEntities struct {
	PostID         string          `json:"postId"`
	ContentType    string          `json:"contentType"`
	EntityMentions []entityMention `json:"entityMentions"`
}
type entityMention struct {
	SubjectType string `json:"subjectType"`
	SubjectID   string `json:"subjectId"`
	HomepageID  string `json:"homepageId"`
	DisplayName string `json:"displayName"`
	RangeStart  int64  `json:"rangeStart"`
	RangeEnd    int64  `json:"rangeEnd"`
}

func projectContentPostDetailArticleEntities(detail postports.PostDetailSlice) (any, error) {
	postID, contentType, err := requiredIdentity(detail)
	if err != nil {
		return nil, err
	}
	if contentType != "article" {
		return nil, fmt.Errorf("article entities slice does not apply to contentType=%s", contentType)
	}
	if len(detail.EntityMentions) > maxArticleEntityRows {
		return nil, errors.New("article entity mentions exceed the object-owned 30 item bound")
	}
	rows := make([]entityMention, len(detail.EntityMentions))
	for index, row := range detail.EntityMentions {
		subjectType, err := requiredString(row.SubjectType, fmt.Sprintf("entityMentions[%d].subjectType", index))
		if err != nil {
			return nil, err
		}
		subjectID, err := requiredString(row.SubjectID, fmt.Sprintf("entityMentions[%d].subjectId", index))
		if err != nil {
			return nil, err
		}
		homepageID, err := requiredString(row.HomepageID, fmt.Sprintf("entityMentions[%d].homepageId", index))
		if err != nil {
			return nil, err
		}
		displayName, err := requiredString(row.DisplayName, fmt.Sprintf("entityMentions[%d].displayName", index))
		if err != nil {
			return nil, err
		}
		if row.RangeStart < 0 || row.RangeEnd < row.RangeStart {
			return nil, fmt.Errorf("entityMentions[%d] has an invalid range", index)
		}
		rows[index] = entityMention{SubjectType: subjectType, SubjectID: subjectID, HomepageID: homepageID,
			DisplayName: displayName, RangeStart: row.RangeStart, RangeEnd: row.RangeEnd}
	}
	return contentPostDetailArticleEntities{PostID: postID, ContentType: contentType, EntityMentions: rows}, nil
}

func requiredIdentity(detail postports.PostDetailSlice) (string, string, error) {
	postID, err := requiredString(string(detail.PostID), "postId")
	if err != nil {
		return "", "", err
	}
	contentType, err := requiredString(string(detail.ContentType), "contentType")
	if err != nil {
		return "", "", err
	}
	if _, ok := supportedContentTypes[contentType]; !ok {
		return "", "", fmt.Errorf("contentType=%s is outside the bundle", contentType)
	}
	return postID, contentType, nil
}

func requiredString(value, name string) (string, error) {
	if strings.TrimSpace(value) == "" {
		return "", fmt.Errorf("%s is required", name)
	}
	return value, nil
}
func nullable(value string) *string {
	if value == "" {
		return nil
	}
	copy := value
	return &copy
}
func formatTime(value time.Time) string { return value.UTC().Format(time.RFC3339Nano) }
func nullableTime(value time.Time) *string {
	if value.IsZero() {
		return nil
	}
	formatted := formatTime(value)
	return &formatted
}
func positiveInt64(value int64) *int64 {
	if value <= 0 {
		return nil
	}
	return int64Pointer(value)
}
func int64Pointer(value int64) *int64 { copy := value; return &copy }
func cloneStrings(values []string) []string {
	if values == nil {
		return nil
	}
	return append([]string(nil), values...)
}
