package application

import (
	"strings"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

type OwnerSearchResponse struct {
	SearchRequestID  string                      `json:"searchRequestId"`
	InterpretedQuery OwnerSearchInterpretedQuery `json:"interpretedQuery"`
	Hits             []OwnerSearchHit            `json:"hits"`
	Citations        []OwnerSearchCitation       `json:"citations"`
	Facets           []rtsearch.Facet            `json:"facets"`
	DegradeSignals   []rtsearch.DegradeSignal    `json:"degradeSignals"`
	Provenance       OwnerSearchProvenance       `json:"provenance"`
	NextCursor       string                      `json:"nextCursor"`
}

type OwnerSearchInterpretedQuery struct {
	Normalized          string   `json:"normalized"`
	Tokens              []string `json:"tokens"`
	Variants            []string `json:"variants"`
	DetectedEntities    []string `json:"detectedEntities"`
	DetectedTags        []string `json:"detectedTags"`
	SelectedObjectTypes []string `json:"selectedObjectTypes"`
}

type OwnerSearchHit struct {
	ObjectRef    string              `json:"objectRef"`
	ObjectType   string              `json:"objectType"`
	ContentType  string              `json:"contentType,omitempty"`
	Title        string              `json:"title"`
	Snippet      string              `json:"snippet,omitempty"`
	Action       string              `json:"action,omitempty"`
	ThumbnailURL string              `json:"thumbnailUrl,omitempty"`
	RankPosition int                 `json:"rankPosition"`
	MatchedTerms []string            `json:"matchedTerms"`
	RankReasons  []rtsearch.Reason   `json:"rankReasons"`
	Evidence     []rtsearch.Evidence `json:"evidence"`
}

type OwnerSearchCitation struct {
	CitationID  string `json:"citationId"`
	ObjectRef   string `json:"objectRef"`
	ObjectType  string `json:"objectType"`
	ContentType string `json:"contentType,omitempty"`
	Title       string `json:"title"`
	Snippet     string `json:"snippet,omitempty"`
	URL         string `json:"url,omitempty"`
	DeepLink    string `json:"deepLink,omitempty"`
}

type OwnerSearchProvenance struct {
	Source      string    `json:"source"`
	GeneratedAt time.Time `json:"generatedAt"`
}

func projectOwnerSearchResponse(
	codec *SearchCursorCodec,
	interpreted rtsearch.InterpretedQuery,
	response rtsearch.RetrieveResponse,
	nextCursor string,
) (OwnerSearchResponse, error) {
	result := OwnerSearchResponse{
		InterpretedQuery: OwnerSearchInterpretedQuery{
			Normalized:          interpreted.Normalized,
			Tokens:              append([]string{}, interpreted.Tokens...),
			Variants:            append([]string{}, interpreted.Variants...),
			DetectedEntities:    append([]string{}, interpreted.DetectedEntities...),
			DetectedTags:        append([]string{}, interpreted.DetectedTags...),
			SelectedObjectTypes: append([]string{}, interpreted.SelectedObjectTypes...),
		},
		Hits:           make([]OwnerSearchHit, 0, len(response.Hits)),
		Citations:      make([]OwnerSearchCitation, 0, len(response.Citations)),
		Facets:         append([]rtsearch.Facet{}, response.Facets...),
		DegradeSignals: append([]rtsearch.DegradeSignal{}, response.DegradeSignals...),
		Provenance:     OwnerSearchProvenance{Source: "search_index_view", GeneratedAt: response.Provenance.GeneratedAt},
		NextCursor:     nextCursor,
	}
	objectRefs := make(map[string]string, len(response.Hits)+len(response.Citations))
	objectRef := func(objectType, objectID string) (string, error) {
		key := strings.TrimSpace(objectType) + "\x00" + strings.TrimSpace(objectID)
		if value := objectRefs[key]; value != "" {
			return value, nil
		}
		value, err := codec.encodeObjectReference(objectType, objectID)
		if err != nil {
			return "", err
		}
		objectRefs[key] = value
		return value, nil
	}
	for _, hit := range response.Hits {
		encodedRef, err := objectRef(hit.ObjectType, hit.ObjectID)
		if err != nil {
			return OwnerSearchResponse{}, err
		}
		result.Hits = append(result.Hits, OwnerSearchHit{
			ObjectRef: encodedRef, ObjectType: strings.TrimSpace(hit.ObjectType),
			ContentType: contentTypeForOwnerHit(hit), Title: strings.TrimSpace(hit.Title),
			Snippet: strings.TrimSpace(hit.Snippet), Action: strings.TrimSpace(hit.DeepLink),
			ThumbnailURL: strings.TrimSpace(hit.ThumbnailURL),
			RankPosition: hit.RankPosition,
			MatchedTerms: append([]string{}, hit.MatchedTerms...),
			RankReasons:  append([]rtsearch.Reason{}, hit.RankReasons...),
			Evidence:     append([]rtsearch.Evidence{}, hit.Evidence...),
		})
	}
	for _, citation := range response.Citations {
		encodedRef, err := objectRef(citation.ObjectType, citation.ObjectID)
		if err != nil {
			return OwnerSearchResponse{}, err
		}
		result.Citations = append(result.Citations, OwnerSearchCitation{
			CitationID: strings.TrimSpace(citation.CitationID), ObjectRef: encodedRef,
			ObjectType: strings.TrimSpace(citation.ObjectType), ContentType: strings.TrimSpace(citation.ContentType),
			Title: strings.TrimSpace(citation.Title), Snippet: strings.TrimSpace(citation.Snippet),
			URL: strings.TrimSpace(citation.URL), DeepLink: strings.TrimSpace(citation.DeepLink),
		})
	}
	return result, nil
}

func contentTypeForOwnerHit(hit rtsearch.RetrieveHit) string {
	if value, ok := hit.Payload["contentType"].(string); ok {
		return strings.TrimSpace(value)
	}
	switch hit.Target {
	case rtsearch.TargetArticle:
		return "article"
	case rtsearch.TargetPhoto:
		return "image"
	case rtsearch.TargetVideo:
		return "video"
	default:
		return ""
	}
}
