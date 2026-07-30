package http

import (
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// canonicalSearchHitWire is the search-service-owned wire truth. Runtime
// retrieve remains an internal orchestration contract; the HTTP boundary
// materializes one bounded public shape and never exposes arbitrary content
// payload maps.
type canonicalSearchHitWire struct {
	Target             rtsearch.Target                 `json:"target"`
	ObjectType         string                          `json:"objectType"`
	ObjectID           string                          `json:"objectId"`
	Title              string                          `json:"title"`
	Snippet            string                          `json:"snippet,omitempty"`
	Score              float64                         `json:"score"`
	MatchedTerms       []string                        `json:"matchedTerms,omitempty"`
	MatchedTags        []string                        `json:"matchedTags,omitempty"`
	Evidence           []rtsearch.Evidence             `json:"evidence,omitempty"`
	Geo                *rtsearch.GeoPoint              `json:"geo,omitempty"`
	DistanceKm         float64                         `json:"distanceKm,omitempty"`
	PlaceName          string                          `json:"placeName,omitempty"`
	ConnectionState    string                          `json:"connectionState,omitempty"`
	IntersectionReason *rtsearch.HitIntersectionReason `json:"intersectionReason,omitempty"`
	RankReasons        []rtsearch.Reason               `json:"rankReasons,omitempty"`
	RankPosition       int                             `json:"rankPosition,omitempty"`
	Content            *canonicalSearchContentHitWire  `json:"content,omitempty"`
	Payload            *canonicalSearchPayloadWire     `json:"payload,omitempty"`
}

type canonicalSearchContentHitWire struct {
	PostID            string `json:"postId"`
	ContentType       string `json:"contentType"`
	ContentIdentity   string `json:"contentIdentity,omitempty"`
	Title             string `json:"title,omitempty"`
	Summary           string `json:"summary,omitempty"`
	CoverURL          string `json:"coverUrl,omitempty"`
	AuthorID          string `json:"authorId,omitempty"`
	AuthorDisplayName string `json:"authorDisplayName,omitempty"`
	AuthorAvatarURL   string `json:"authorAvatarUrl,omitempty"`
	CategoryID        string `json:"categoryId,omitempty"`
	SubCategory       string `json:"subCategory,omitempty"`
	LikeCount         int    `json:"likeCount"`
	PublishedAt       string `json:"publishedAt,omitempty"`
}

// canonicalSearchPayloadWire is intentionally bounded. It is used only by
// non-content hits; content.post must use canonicalSearchContentHitWire.
type canonicalSearchPayloadWire struct {
	CoverURL            string `json:"coverUrl,omitempty"`
	PlaceName           string `json:"placeName,omitempty"`
	Address             string `json:"address,omitempty"`
	FollowerCount       *int   `json:"followerCount,omitempty"`
	ContentCount        *int   `json:"contentCount,omitempty"`
	CircleID            string `json:"circleId,omitempty"`
	CategoryID          string `json:"categoryId,omitempty"`
	SubCategory         string `json:"subCategory,omitempty"`
	DomainID            string `json:"domainId,omitempty"`
	Kind                string `json:"kind,omitempty"`
	DisplaySubjectType  string `json:"displaySubjectType,omitempty"`
	MemberCount         *int   `json:"memberCount,omitempty"`
	PostCount           *int   `json:"postCount,omitempty"`
	CircleName          string `json:"circleName,omitempty"`
	LinkedHomepageID    string `json:"linkedHomepageId,omitempty"`
	LinkedHomepageType  string `json:"linkedHomepageType,omitempty"`
	LinkedHomepageTitle string `json:"linkedHomepageTitle,omitempty"`
}

func canonicalSearchHits(hits []rtsearch.RetrieveHit) []canonicalSearchHitWire {
	result := make([]canonicalSearchHitWire, 0, len(hits))
	for _, hit := range hits {
		result = append(result, CanonicalSearchHit(hit))
	}
	return result
}

// CanonicalSearchHit materializes the bounded public search wire for contract
// verification. The package remains service-internal; arbitrary retrieve
// payloads never cross this boundary.
func CanonicalSearchHit(hit rtsearch.RetrieveHit) canonicalSearchHitWire {
	wire := canonicalSearchHitWire{
		Target: hit.Target, ObjectType: strings.TrimSpace(hit.ObjectType),
		ObjectID: strings.TrimSpace(hit.ObjectID), Title: strings.TrimSpace(hit.Title),
		Snippet: strings.TrimSpace(hit.Snippet), Score: hit.Score,
		MatchedTerms: append([]string(nil), hit.MatchedTerms...),
		MatchedTags:  append([]string(nil), hit.MatchedTags...),
		Evidence:     append([]rtsearch.Evidence(nil), hit.Evidence...),
		Geo:          cloneSearchGeo(hit.Geo), DistanceKm: hit.DistanceKm,
		PlaceName:          strings.TrimSpace(hit.PlaceName),
		ConnectionState:    strings.TrimSpace(hit.ConnectionState),
		IntersectionReason: cloneIntersectionReason(hit.IntersectionReason),
		RankReasons:        append([]rtsearch.Reason(nil), hit.RankReasons...),
		RankPosition:       hit.RankPosition,
	}
	if contentType := canonicalContentType(hit.Target, hit.Payload); contentType != "" {
		wire.Content = &canonicalSearchContentHitWire{
			PostID: wire.ObjectID, ContentType: contentType,
			ContentIdentity: payloadText(hit.Payload, "contentIdentity"),
			Title:           wire.Title, Summary: wire.Snippet,
			CoverURL:          payloadText(hit.Payload, "coverUrl"),
			AuthorID:          payloadText(hit.Payload, "authorId"),
			AuthorDisplayName: payloadText(hit.Payload, "authorDisplayName"),
			AuthorAvatarURL:   payloadText(hit.Payload, "authorAvatarUrl"),
			CategoryID:        payloadText(hit.Payload, "categoryId"),
			SubCategory:       payloadText(hit.Payload, "subCategory"),
			LikeCount:         payloadIntValue(hit.Payload, "likeCount"),
			PublishedAt:       payloadText(hit.Payload, "publishedAt"),
		}
		return wire
	}
	wire.Payload = canonicalNonContentPayload(hit.Payload)
	return wire
}

func canonicalContentType(target rtsearch.Target, payload map[string]any) string {
	switch target {
	case rtsearch.TargetPhoto:
		return "image"
	case rtsearch.TargetVideo:
		return "video"
	case rtsearch.TargetArticle:
		if value := payloadText(payload, "contentType"); value != "" {
			return value
		}
		return "article"
	default:
		return ""
	}
}

func canonicalNonContentPayload(payload map[string]any) *canonicalSearchPayloadWire {
	if len(payload) == 0 {
		return nil
	}
	wire := &canonicalSearchPayloadWire{
		CoverURL:  payloadText(payload, "coverUrl"),
		PlaceName: payloadText(payload, "placeName"), Address: payloadText(payload, "address"),
		FollowerCount: payloadInt(payload, "followerCount"), ContentCount: payloadInt(payload, "contentCount"),
		CircleID: payloadText(payload, "circleId"), CategoryID: payloadText(payload, "categoryId"),
		SubCategory: payloadText(payload, "subCategory"), DomainID: payloadText(payload, "domainId"),
		Kind: payloadText(payload, "kind"), DisplaySubjectType: payloadText(payload, "displaySubjectType"),
		MemberCount: payloadInt(payload, "memberCount"), PostCount: payloadInt(payload, "postCount"),
		CircleName: payloadText(payload, "circleName"), LinkedHomepageID: payloadText(payload, "linkedHomepageId"),
		LinkedHomepageType:  payloadText(payload, "linkedHomepageType"),
		LinkedHomepageTitle: payloadText(payload, "linkedHomepageTitle"),
	}
	if *wire == (canonicalSearchPayloadWire{}) {
		return nil
	}
	return wire
}

func payloadText(payload map[string]any, key string) string {
	value, _ := payload[key].(string)
	return strings.TrimSpace(value)
}

func payloadInt(payload map[string]any, key string) *int {
	var value int
	switch raw := payload[key].(type) {
	case int:
		value = raw
	case int32:
		value = int(raw)
	case int64:
		value = int(raw)
	case float64:
		value = int(raw)
	default:
		return nil
	}
	return &value
}

func payloadIntValue(payload map[string]any, key string) int {
	if value := payloadInt(payload, key); value != nil {
		return *value
	}
	return 0
}

func cloneSearchGeo(value *rtsearch.GeoPoint) *rtsearch.GeoPoint {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}

func cloneIntersectionReason(value *rtsearch.HitIntersectionReason) *rtsearch.HitIntersectionReason {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
