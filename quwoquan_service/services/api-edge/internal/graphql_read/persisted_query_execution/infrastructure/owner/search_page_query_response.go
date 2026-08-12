package owner

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"
)

// searchOwnerResponse mirrors the bounded OwnerSearchResponseView. It
// intentionally has no score, index, embedding, features, raw objectId, or
// arbitrary payload field, so DisallowUnknownFields rejects backend leakage.
type searchOwnerResponse struct {
	InterpretedQuery searchOwnerInterpretedQuery `json:"interpretedQuery"`
	Hits             []searchOwnerHit            `json:"hits"`
	Citations        []searchOwnerCitation       `json:"citations"`
	Facets           []searchOwnerFacet          `json:"facets"`
	DegradeSignals   []searchOwnerDegradeSignal  `json:"degradeSignals"`
	Provenance       searchOwnerProvenance       `json:"provenance"`
	NextCursor       string                      `json:"nextCursor,omitempty"`
}

type searchOwnerInterpretedQuery struct {
	Normalized          string   `json:"normalized"`
	Tokens              []string `json:"tokens"`
	Variants            []string `json:"variants"`
	DetectedEntities    []string `json:"detectedEntities"`
	DetectedTags        []string `json:"detectedTags"`
	SelectedObjectTypes []string `json:"selectedObjectTypes"`
}

type searchOwnerHit struct {
	ObjectRef    string `json:"objectRef"`
	ObjectType   string `json:"objectType"`
	ContentType  string `json:"contentType,omitempty"`
	Title        string `json:"title"`
	Snippet      string `json:"snippet,omitempty"`
	ThumbnailURL string `json:"thumbnailUrl,omitempty"`
	Action       string `json:"action,omitempty"`
}

type searchOwnerCitation struct {
	CitationID  string `json:"citationId"`
	ObjectRef   string `json:"objectRef"`
	ObjectType  string `json:"objectType"`
	ContentType string `json:"contentType,omitempty"`
	Title       string `json:"title"`
	Snippet     string `json:"snippet,omitempty"`
	URL         string `json:"url,omitempty"`
	DeepLink    string `json:"deepLink,omitempty"`
}

type searchOwnerFacet struct {
	Key   string `json:"key"`
	Label string `json:"label"`
	Count int    `json:"count"`
}

type searchOwnerDegradeSignal struct {
	Code       string `json:"code"`
	Message    string `json:"message"`
	ObjectType string `json:"objectType,omitempty"`
}

type searchOwnerProvenance struct {
	Source      string `json:"source"`
	GeneratedAt string `json:"generatedAt"`
}

type searchPageData struct {
	Items       []searchPageItem  `json:"items"`
	Facets      []searchPageFacet `json:"facets"`
	Suggestions []string          `json:"suggestions"`
	NextCursor  *string           `json:"nextCursor"`
}

type searchPageItem struct {
	ObjectRef    string  `json:"objectRef"`
	ResultType   string  `json:"resultType"`
	Title        string  `json:"title"`
	Subtitle     *string `json:"subtitle"`
	Snippet      *string `json:"snippet"`
	ThumbnailURL *string `json:"thumbnailUrl"`
	Action       string  `json:"action"`
}

type searchPageFacet struct {
	Key   string `json:"key"`
	Count int    `json:"count"`
}

func decodeSearchOwnerPage(encoded []byte, pageSize int) (searchPageData, error) {
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.DisallowUnknownFields()
	var owner searchOwnerResponse
	if err := decoder.Decode(&owner); err != nil {
		return searchPageData{}, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); !errors.Is(err, io.EOF) {
		return searchPageData{}, errors.New("SearchPage owner response must contain one JSON object")
	}
	if owner.Hits == nil || owner.Citations == nil || owner.Facets == nil ||
		owner.DegradeSignals == nil || owner.InterpretedQuery.Tokens == nil ||
		owner.InterpretedQuery.Variants == nil || owner.InterpretedQuery.DetectedEntities == nil ||
		owner.InterpretedQuery.DetectedTags == nil || owner.InterpretedQuery.SelectedObjectTypes == nil {
		return searchPageData{}, errors.New("SearchPage owner response contains a nullable collection")
	}
	if len(owner.DegradeSignals) != 0 {
		return searchPageData{}, errors.New("SearchPage owner returned a partial/degraded result")
	}
	if len(owner.Hits) > pageSize || len(owner.Facets) > pageSize || len(owner.InterpretedQuery.Variants) > pageSize {
		return searchPageData{}, errors.New("SearchPage owner exceeded the requested page bound")
	}
	if strings.TrimSpace(owner.Provenance.Source) != "search_index_view" {
		return searchPageData{}, errors.New("SearchPage owner provenance source is invalid")
	}
	if _, err := time.Parse(time.RFC3339Nano, owner.Provenance.GeneratedAt); err != nil {
		return searchPageData{}, errors.New("SearchPage owner provenance time is invalid")
	}
	var nextCursor *string
	if owner.NextCursor != "" {
		validated, err := boundedText(owner.NextCursor, "nextCursor", maxSearchCursorBytes, false)
		if err != nil {
			return searchPageData{}, err
		}
		nextCursor = &validated
	}
	items := make([]searchPageItem, 0, len(owner.Hits))
	seenRefs := map[string]bool{}
	for index, hit := range owner.Hits {
		item, err := projectSearchPageItem(hit)
		if err != nil {
			return searchPageData{}, fmt.Errorf("SearchPage owner hit %d: %w", index, err)
		}
		if seenRefs[item.ObjectRef] {
			return searchPageData{}, errors.New("SearchPage owner returned duplicate objectRef")
		}
		seenRefs[item.ObjectRef] = true
		items = append(items, item)
	}
	facets := make([]searchPageFacet, 0, len(owner.Facets))
	seenFacets := map[string]bool{}
	for _, facet := range owner.Facets {
		key, err := boundedText(facet.Key, "facet key", 256, false)
		if err != nil || facet.Count < 0 || seenFacets[key] {
			return searchPageData{}, errors.New("SearchPage owner facet is invalid or duplicated")
		}
		seenFacets[key] = true
		facets = append(facets, searchPageFacet{Key: key, Count: facet.Count})
	}
	suggestions := make([]string, 0, len(owner.InterpretedQuery.Variants))
	seenSuggestions := map[string]bool{}
	for _, value := range owner.InterpretedQuery.Variants {
		term, err := boundedText(value, "suggestion", maxSearchQueryBytes, false)
		if err != nil || seenSuggestions[term] {
			return searchPageData{}, errors.New("SearchPage owner suggestion is invalid or duplicated")
		}
		seenSuggestions[term] = true
		suggestions = append(suggestions, term)
	}
	return searchPageData{
		Items: items, Facets: facets, Suggestions: suggestions, NextCursor: nextCursor,
	}, nil
}

func projectSearchPageItem(hit searchOwnerHit) (searchPageItem, error) {
	objectRef, err := boundedText(hit.ObjectRef, "objectRef", maxSearchIdentityBytes, false)
	if err != nil {
		return searchPageItem{}, err
	}
	resultType, ok := searchPageObjectTypeForCanonical(hit.ObjectType)
	if !ok {
		return searchPageItem{}, errors.New("objectType is outside the SearchPage closed set")
	}
	title, err := boundedText(hit.Title, "title", 4096, false)
	if err != nil {
		return searchPageItem{}, err
	}
	snippet, err := optionalText(hit.Snippet, "snippet", 8192)
	if err != nil {
		return searchPageItem{}, err
	}
	thumbnailURL, err := optionalText(hit.ThumbnailURL, "thumbnailUrl", 8192)
	if err != nil {
		return searchPageItem{}, err
	}
	action, err := boundedText(hit.Action, "action", 4096, false)
	if err != nil {
		return searchPageItem{}, err
	}
	return searchPageItem{
		ObjectRef: objectRef, ResultType: resultType, Title: title,
		Subtitle: nil, Snippet: snippet, ThumbnailURL: thumbnailURL, Action: action,
	}, nil
}

func searchPageObjectTypeForCanonical(value string) (string, bool) {
	for enumValue, canonical := range searchObjectTypeBindings {
		if value == canonical {
			return enumValue, true
		}
	}
	return "", false
}

func boundedText(value, label string, maximum int, allowEmpty bool) (string, error) {
	trimmed := strings.TrimSpace(value)
	if (!allowEmpty && trimmed == "") || trimmed != value || len(trimmed) > maximum || containsControl(trimmed) {
		return "", fmt.Errorf("SearchPage owner %s is invalid", label)
	}
	return trimmed, nil
}

func optionalText(value, label string, maximum int) (*string, error) {
	if value == "" {
		return nil, nil
	}
	validated, err := boundedText(value, label, maximum, false)
	if err != nil {
		return nil, err
	}
	return &validated, nil
}
