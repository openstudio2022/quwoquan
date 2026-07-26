package homepage

import (
	"encoding/json"
	"time"

	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
)

type GeoPoint = homepagemodel.GeoPoint
type IntroductionAsset = homepagemodel.IntroductionAsset
type Source = homepagemodel.Source
type ReviewSummary = homepagemodel.ReviewSummary
type ContentPreview = homepagemodel.ContentPreview
type QuestionPreview = homepagemodel.QuestionPreview
type RelatedGroup = homepagemodel.RelatedGroup

type View struct {
	ID                   string              `json:"homepageId"`
	Version              int64               `json:"-"`
	Title                string              `json:"title"`
	Subtitle             string              `json:"subtitle,omitempty"`
	HomepageType         string              `json:"homepageType"`
	CanonicalEntityID    string              `json:"-"`
	LookupAliases        []string            `json:"-"`
	ObjectPageTemplate   string              `json:"-"`
	Status               string              `json:"status"`
	SourceType           string              `json:"-"`
	SourceOwner          string              `json:"-" bson:"sourceOwner,omitempty"`
	SourceEntityRef      string              `json:"-" bson:"sourceEntityRef,omitempty"`
	SourceReleaseID      string              `json:"-" bson:"sourceReleaseId,omitempty"`
	ClaimStatus          string              `json:"claimStatus"`
	CategoryTags         []string            `json:"categoryTags,omitempty"`
	CoverURL             string              `json:"coverUrl,omitempty"`
	Address              string              `json:"address,omitempty"`
	City                 string              `json:"city,omitempty"`
	Location             *GeoPoint           `json:"location,omitempty"`
	OwnerUserID          string              `json:"ownerUserId,omitempty"`
	OwnerSubAccountID    string              `json:"ownerSubAccountId,omitempty"`
	ViewerFollows        bool                `json:"viewerFollowsHomepage"`
	FollowerCount        int                 `json:"followerCount"`
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
	PrimarySource        *Source             `json:"primarySource,omitempty"`
	SourceURLs           []string            `json:"sourceUrls"`
	CreatedAt            time.Time           `json:"createdAt"`
	UpdatedAt            time.Time           `json:"updatedAt"`
	PublishedAt          *time.Time          `json:"publishedAt,omitempty"`
	OfflineAt            *time.Time          `json:"offlineAt,omitempty"`
}

type Input struct {
	Title                string              `json:"title"`
	Subtitle             string              `json:"subtitle"`
	HomepageType         string              `json:"homepageType"`
	CanonicalEntityID    string              `json:"canonicalEntityId"`
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
	HomepageID        string   `json:"homepageId"`
	CanonicalEntityID string   `json:"-"`
	Title             string   `json:"title"`
	Subtitle          string   `json:"subtitle,omitempty"`
	HomepageType      string   `json:"homepageType"`
	CoverURL          string   `json:"coverUrl,omitempty"`
	City              string   `json:"city,omitempty"`
	Address           string   `json:"address,omitempty"`
	Status            string   `json:"status"`
	AverageRating     *float64 `json:"averageRating,omitempty"`
	RatingCount       int      `json:"ratingCount"`
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

func ViewFromSnapshot(snapshot homepagemodel.Snapshot) View {
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
		Address:              snapshot.Address,
		City:                 snapshot.City,
		Location:             cloneGeo(snapshot.Location),
		OwnerUserID:          snapshot.OwnerUserID,
		OwnerSubAccountID:    snapshot.OwnerSubAccountID,
		Verified:             snapshot.Verified,
		EstablishedYear:      cloneInt(snapshot.EstablishedYear),
		AverageRating:        cloneFloat(snapshot.AverageRating),
		RatingCount:          snapshot.RatingCount,
		ReviewSummary:        cloneReviewSummary(snapshot.ReviewSummary),
		AssistantContext:     append(json.RawMessage(nil), snapshot.AssistantContext...),
		IntroductionMarkdown: snapshot.IntroductionMarkdown,
		IntroductionAssets:   append([]IntroductionAsset{}, snapshot.IntroductionAssets...),
		PrimarySource:        cloneSource(snapshot.PrimarySource),
		CreatedAt:            snapshot.CreatedAt,
		UpdatedAt:            snapshot.UpdatedAt,
		PublishedAt:          cloneTime(snapshot.PublishedAt),
		OfflineAt:            cloneTime(snapshot.OfflineAt),
		ContentPreview:       emptyIfNil(snapshot.ContentPreview),
		QuestionPreview:      emptyIfNil(snapshot.QuestionPreview),
		RelatedGroups:        emptyIfNil(snapshot.RelatedGroups),
		RelationEdges:        emptyRawIfNil(snapshot.RelationEdges),
		SourceURLs:           emptyStringsIfNil(snapshot.SourceURLs),
	}
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
