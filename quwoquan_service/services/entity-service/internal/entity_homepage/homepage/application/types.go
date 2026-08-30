package homepage

import (
	"encoding/json"
	"strings"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type GeoPoint = homepagemodel.GeoPoint
type IntroductionAsset = homepagemodel.IntroductionAsset
type Source = homepagemodel.Source
type ReviewSummary = homepagemodel.ReviewSummary
type ContentPreview = homepagemodel.ContentPreview
type QuestionPreview = homepagemodel.QuestionPreview
type RelatedGroup = homepagemodel.RelatedGroup
type StructuredFacts = homepagemodel.StructuredFacts

type ViewerFollowSlice struct {
	ViewerFollowsHomepage bool `json:"viewerFollowsHomepage"`
	FollowerCount         int  `json:"followerCount"`
}

type View struct {
	ID                 string   `json:"homepageId"`
	Version            int64    `json:"-"`
	Title              string   `json:"title"`
	Subtitle           string   `json:"subtitle,omitempty"`
	HomepageType       string   `json:"homepageType"`
	CanonicalEntityID  string   `json:"-"`
	LookupAliases      []string `json:"-"`
	ObjectPageTemplate string   `json:"-"`
	Status             string   `json:"status"`
	SourceType         string   `json:"-"`
	SourceOwner        string   `json:"-" bson:"sourceOwner,omitempty"`
	SourceEntityRef    string   `json:"-" bson:"sourceEntityRef,omitempty"`
	SourceReleaseID    string   `json:"-" bson:"sourceReleaseId,omitempty"`
	ClaimStatus        string   `json:"claimStatus"`
	CategoryTags       []string `json:"categoryTags,omitempty"`
	CoverURL           string   `json:"coverUrl,omitempty"`
	// cover 的配对媒体资产标识与交付访问模式（DEC-033，contracts
	// projections/homepage_detail_view.yaml coverAssetId/coverAccessMode）。
	// signed_grant 时 App 以 coverAssetId 换取短签；禁止以 homepageId 冒充
	// 媒体资产标识，也禁止按 coverUrl 形态反推交付形态。
	CoverAssetID         string              `json:"coverAssetId,omitempty"`
	CoverAccessMode      string              `json:"coverAccessMode,omitempty"`
	Address              string              `json:"address,omitempty"`
	City                 string              `json:"city,omitempty"`
	Location             *GeoPoint           `json:"location,omitempty"`
	OwnerUserID          string              `json:"ownerUserId,omitempty"`
	OwnerPersonaID       string              `json:"ownerPersonaId,omitempty"`
	ViewerFollow         ViewerFollowSlice   `json:"viewerFollow"`
	Verified             bool                `json:"verified"`
	EstablishedYear      *int                `json:"establishedYear,omitempty"`
	AverageRating        *float64            `json:"averageRating,omitempty"`
	RatingCount          int                 `json:"ratingCount"`
	ReviewSummary        *ReviewSummary      `json:"reviewSummary,omitempty"`
	ContentPreview       []ContentPreview    `json:"contentPreview"`
	QuestionPreview      []QuestionPreview   `json:"questionPreview"`
	RelatedGroups        []RelatedGroup      `json:"relatedGroups"`
	RelationEdges        []json.RawMessage   `json:"relationEdges"`
	AssistantContext     json.RawMessage     `json:"assistantContext,omitempty"`
	IntroductionMarkdown string              `json:"introductionMarkdown,omitempty"`
	IntroductionAssets   []IntroductionAsset `json:"introductionAssets,omitempty"`
	StructuredFacts      *StructuredFacts    `json:"structuredFacts,omitempty"`
	PrimarySource        *Source             `json:"primarySource,omitempty"`
	SourceURLs           []string            `json:"sourceUrls"`
	CreatedAt            time.Time           `json:"createdAt"`
	UpdatedAt            time.Time           `json:"updatedAt"`
	PublishedAt          *time.Time          `json:"publishedAt,omitempty"`
	OfflineAt            *time.Time          `json:"offlineAt,omitempty"`
}

type Input struct {
	Title             string `json:"title"`
	Subtitle          string `json:"subtitle"`
	HomepageType      string `json:"homepageType"`
	CanonicalEntityID string `json:"canonicalEntityId"`
	// LookupAliases is an internal projection identity set. The public suggest
	// endpoint maps its single validated sourcePlaceId into this field; raw
	// aliases are never accepted from the request body.
	LookupAliases        []string            `json:"-"`
	ObjectPageTemplate   string              `json:"objectPageTemplate"`
	CategoryTags         []string            `json:"categoryTags"`
	CoverURL             string              `json:"coverUrl"`
	Address              string              `json:"address"`
	City                 string              `json:"city"`
	Location             *GeoPoint           `json:"location"`
	IntroductionMarkdown string              `json:"introductionMarkdown"`
	IntroductionAssets   []IntroductionAsset `json:"introductionAssets"`
}

type BasicInput struct {
	Title           string    `json:"title"`
	Subtitle        string    `json:"subtitle"`
	CategoryTags    []string  `json:"categoryTags"`
	CoverURL        string    `json:"coverUrl"`
	Address         string    `json:"address"`
	City            string    `json:"city"`
	Location        *GeoPoint `json:"location"`
	Verified        *bool     `json:"verified,omitempty"`
	EstablishedYear *int      `json:"establishedYear,omitempty"`
}

type SearchItemView struct {
	HomepageID        string `json:"homepageId"`
	CanonicalEntityID string `json:"-"`
	Title             string `json:"title"`
	Subtitle          string `json:"subtitle,omitempty"`
	HomepageType      string `json:"homepageType"`
	CoverURL          string `json:"coverUrl,omitempty"`
	// cover 的配对媒体资产标识与交付访问模式（DEC-033），与 HomepageDetailView 同源。
	CoverAssetID    string   `json:"coverAssetId,omitempty"`
	CoverAccessMode string   `json:"coverAccessMode,omitempty"`
	City            string   `json:"city,omitempty"`
	Address         string   `json:"address,omitempty"`
	Status          string   `json:"status"`
	AverageRating   *float64 `json:"averageRating,omitempty"`
	RatingCount     int      `json:"ratingCount"`
}

type SearchSlice struct {
	Items      []SearchItemView `json:"items"`
	NextCursor string           `json:"nextCursor,omitempty"`
}

type LifecycleEventPayload struct {
	HomepageID        string    `json:"homepageId"`
	CanonicalEntityID string    `json:"canonicalEntityId"`
	SourceEntityRef   string    `json:"sourceEntityRef,omitempty"`
	Title             string    `json:"title"`
	HomepageType      string    `json:"homepageType"`
	Status            string    `json:"status"`
	ClaimStatus       string    `json:"claimStatus"`
	CategoryTags      []string  `json:"categoryTags"`
	UpdatedAt         time.Time `json:"updatedAt"`
}

func LifecycleEventPayloadFromSnapshot(
	snapshot homepagemodel.Snapshot,
) LifecycleEventPayload {
	return LifecycleEventPayload{
		HomepageID:        snapshot.ID,
		CanonicalEntityID: snapshot.CanonicalEntityID,
		SourceEntityRef:   snapshot.SourceEntityRef,
		Title:             snapshot.Title,
		HomepageType:      snapshot.HomepageType,
		Status:            string(snapshot.Status),
		ClaimStatus:       snapshot.ClaimStatus,
		CategoryTags:      emptyStringsIfNil(snapshot.CategoryTags),
		UpdatedAt:         snapshot.UpdatedAt.UTC(),
	}
}

// detailCoverBinding 把 cover URL 配对回 introductionAssets 的 typed 声明。
//
// 与 HomepageIntroduction 同一规则：cover 角色优先，避免同 URL 的 inline/related
// 项抢占配对；配不上即两字段都缺席（契约 NULLABLE），不猜一个 accessMode。
func detailCoverBinding(
	coverURL string,
	assets []IntroductionAsset,
) (string, string) {
	coverURL = strings.TrimSpace(coverURL)
	if coverURL == "" {
		return "", ""
	}
	for _, asset := range assets {
		if asset.Role == "cover" && strings.TrimSpace(asset.URL) == coverURL {
			return strings.TrimSpace(asset.AssetID), strings.TrimSpace(asset.AccessMode)
		}
	}
	for _, asset := range assets {
		if strings.TrimSpace(asset.URL) == coverURL {
			return strings.TrimSpace(asset.AssetID), strings.TrimSpace(asset.AccessMode)
		}
	}
	return "", ""
}

func ViewFromSnapshot(snapshot homepagemodel.Snapshot) View {
	coverAssetID, coverAccessMode := detailCoverBinding(
		snapshot.CoverURL,
		snapshot.IntroductionAssets,
	)
	return View{
		ID:                   snapshot.ID,
		Version:              snapshot.Version,
		Title:                snapshot.Title,
		Subtitle:             snapshot.Subtitle,
		HomepageType:         snapshot.HomepageType,
		CanonicalEntityID:    snapshot.CanonicalEntityID,
		LookupAliases:        cloneStrings(snapshot.LookupAliases),
		ObjectPageTemplate:   snapshot.ObjectPageTemplate,
		Status:               string(snapshot.Status),
		SourceType:           snapshot.SourceType,
		SourceOwner:          snapshot.SourceOwner,
		SourceEntityRef:      snapshot.SourceEntityRef,
		SourceReleaseID:      snapshot.SourceReleaseID,
		ClaimStatus:          snapshot.ClaimStatus,
		CategoryTags:         cloneStrings(snapshot.CategoryTags),
		CoverURL:             snapshot.CoverURL,
		CoverAssetID:         coverAssetID,
		CoverAccessMode:      coverAccessMode,
		Address:              snapshot.Address,
		City:                 snapshot.City,
		Location:             cloneGeo(snapshot.Location),
		OwnerUserID:          snapshot.OwnerUserID,
		OwnerPersonaID:       snapshot.OwnerPersonaID,
		Verified:             snapshot.Verified,
		EstablishedYear:      cloneInt(snapshot.EstablishedYear),
		IntroductionMarkdown: snapshot.IntroductionMarkdown,
		IntroductionAssets:   append([]IntroductionAsset{}, snapshot.IntroductionAssets...),
		StructuredFacts:      snapshot.StructuredFacts.Clone(),
		PrimarySource:        cloneSource(snapshot.PrimarySource),
		CreatedAt:            snapshot.CreatedAt,
		UpdatedAt:            snapshot.UpdatedAt,
		PublishedAt:          cloneTime(snapshot.PublishedAt),
		OfflineAt:            cloneTime(snapshot.OfflineAt),
		ContentPreview:       []ContentPreview{},
		QuestionPreview:      []QuestionPreview{},
		RelatedGroups:        []RelatedGroup{},
		RelationEdges:        []json.RawMessage{},
		SourceURLs:           emptyStringsIfNil(snapshot.SourceURLs),
	}
}

func ApplyDetailProjection(view View, projection homepageports.DetailProjection) View {
	view.AverageRating = cloneFloat(projection.AverageRating)
	view.RatingCount = projection.RatingCount
	view.ReviewSummary = cloneReviewSummary(projection.ReviewSummary)
	view.ContentPreview = emptyIfNil(projection.ContentPreview)
	view.QuestionPreview = emptyIfNil(projection.QuestionPreview)
	view.RelatedGroups = emptyIfNil(projection.RelatedGroups)
	view.RelationEdges = emptyRawIfNil(projection.RelationEdges)
	view.AssistantContext = append(json.RawMessage(nil), projection.AssistantContext...)
	return view
}

func cloneStrings(values []string) []string { return append([]string(nil), values...) }
func emptyStringsIfNil(values []string) []string {
	return append([]string{}, values...)
}
func cloneGeo(value *homepagemodel.GeoPoint) *GeoPoint {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneSource(value *homepagemodel.Source) *Source {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	result := value.UTC()
	return &result
}
func cloneInt(value *int) *int {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneFloat(value *float64) *float64 {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
func cloneReviewSummary(value *homepagemodel.ReviewSummary) *ReviewSummary {
	if value == nil {
		return nil
	}
	return &ReviewSummary{
		AverageRating: cloneFloat(value.AverageRating),
		RatingCount:   value.RatingCount,
		HighlightTags: cloneStrings(value.HighlightTags),
	}
}
func cloneRawSlice(values []json.RawMessage) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}
func emptyRawIfNil(values []json.RawMessage) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}
func emptyIfNil[T any](values []T) []T {
	return append([]T{}, values...)
}
