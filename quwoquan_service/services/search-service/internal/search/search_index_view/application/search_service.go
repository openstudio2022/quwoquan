// Package application owns the SearchIndexView query use case.
package application

import (
	"context"
	"errors"
	"fmt"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// DefaultResultTargets is the result-page recall scope. chat.* is local_only and
// is intentionally excluded from the cloud search path.
var DefaultResultTargets = []rtsearch.Target{
	rtsearch.TargetArticle, rtsearch.TargetPhoto, rtsearch.TargetVideo,
	rtsearch.TargetUser, rtsearch.TargetEntity, rtsearch.TargetLocation,
}

// SuggestLimit / ResultLimit are the default page sizes when callers omit limit.
const (
	SuggestLimit = 12
	ResultLimit  = 20
)

var ErrSearchInvalid = errors.New("invalid search request")

var ErrSearchForbidden = errors.New("search mode is forbidden for caller")

// SearchService runs the canonical search(request) over the injected backend.
type SearchService struct {
	backend rtsearch.RecallBackend
	cursor  *SearchCursorCodec
}

type SearchServiceOption func(*SearchService)

func WithSearchCursorCodec(codec *SearchCursorCodec) SearchServiceOption {
	return func(service *SearchService) { service.cursor = codec }
}

// NewSearchService builds the query use case.
func NewSearchService(backend rtsearch.RecallBackend, options ...SearchServiceOption) *SearchService {
	service := &SearchService{backend: backend}
	for _, option := range options {
		if option != nil {
			option(service)
		}
	}
	return service
}

// QueryInput is the canonical query-first input shared by App + AI agents.
type QueryInput struct {
	Query       string
	Mode        string
	ObjectTypes []string
	IDs         []string
	Limit       int
	Tags        []string
	TimeRange   *rtsearch.TimeRange
	// Near is the optional 附近 geo radius filter; it spans every target that
	// carries a Geo dimension (entity/content today, user/circle next).
	Near   *rtsearch.GeoNear
	Cursor string
}

type QueryCaller struct {
	PrincipalKey string
	ServiceName  string
	Scopes       []string
}

type QueryExecutionIdentity struct {
	CandidateDigest string
	PolicyDigest    string
}

type QueryExecution struct {
	Response         rtsearch.RetrieveResponse
	InterpretedQuery rtsearch.InterpretedQuery
	NextCursor       string
}

// Search runs the unified retrieve over the backend, mapping the query-first
// input into the frozen RetrieveRequest contract (single-sourced in runtime).
func (s *SearchService) Search(ctx context.Context, in QueryInput, viewer rtsearch.Viewer) (rtsearch.RetrieveResponse, error) {
	execution, err := s.execute(ctx, in, viewer, QueryCaller{PrincipalKey: legacyPrincipalKey(viewer)}, QueryExecutionIdentity{}, false)
	return execution.Response, err
}

func (s *SearchService) Execute(
	ctx context.Context,
	in QueryInput,
	viewer rtsearch.Viewer,
	caller QueryCaller,
	identity QueryExecutionIdentity,
) (QueryExecution, error) {
	return s.execute(ctx, in, viewer, caller, identity, true)
}

func (s *SearchService) ExecuteOwnerQuery(
	ctx context.Context,
	in QueryInput,
	viewer rtsearch.Viewer,
	caller QueryCaller,
	identity QueryExecutionIdentity,
) (OwnerSearchResponse, error) {
	mode := normalizedSearchMode(in.Mode)
	if mode != "suggest" && mode != "result" && mode != "retrieval" {
		return OwnerSearchResponse{}, ErrSearchInvalid
	}
	if !ownerProjectionCaller(caller, mode) {
		return OwnerSearchResponse{}, ErrSearchForbidden
	}
	execution, err := s.execute(ctx, in, viewer, caller, identity, true)
	if err != nil {
		return OwnerSearchResponse{}, err
	}
	return projectOwnerSearchResponse(s.cursor, execution.InterpretedQuery, execution.Response, execution.NextCursor)
}

func normalizedSearchMode(value string) string {
	value = strings.ToLower(strings.TrimSpace(value))
	if value == "" {
		return "result"
	}
	return value
}

func ownerProjectionCaller(caller QueryCaller, mode string) bool {
	switch strings.TrimSpace(caller.ServiceName) {
	case "assistant-service":
		return mode == "retrieval" && callerHasScope(caller, "assistant.search.search_index_view.read")
	case "api-edge":
		return (mode == "suggest" || mode == "result") && callerHasScope(caller, "search.search_index_view.graphql.read")
	default:
		return false
	}
}

func (s *SearchService) execute(
	ctx context.Context,
	in QueryInput,
	viewer rtsearch.Viewer,
	caller QueryCaller,
	identity QueryExecutionIdentity,
	managedCursor bool,
) (QueryExecution, error) {
	mode := normalizedSearchMode(in.Mode)
	if mode != "suggest" && mode != "result" && mode != "retrieval" {
		return QueryExecution{}, ErrSearchInvalid
	}
	if mode == "retrieval" && !assistantRetrievalCaller(caller) {
		return QueryExecution{}, ErrSearchForbidden
	}
	in.Mode = mode
	if err := validateCloudObjectTypes(in.ObjectTypes); err != nil {
		return QueryExecution{}, err
	}
	limit := in.Limit
	if limit <= 0 {
		if strings.EqualFold(in.Mode, "suggest") {
			limit = SuggestLimit
		} else {
			limit = ResultLimit
		}
	}
	if limit > 100 {
		return QueryExecution{}, ErrSearchInvalid
	}
	in.Limit = limit
	offset := 0
	if cursor := strings.TrimSpace(in.Cursor); cursor != "" {
		if !managedCursor || s.cursor == nil {
			return QueryExecution{}, ErrSearchCursor
		}
		decoded, err := s.cursor.decodeCursor(cursor, in, caller, identity)
		if err != nil {
			return QueryExecution{}, err
		}
		offset = decoded
	}
	filters := rtsearch.RetrieveFilters{Tags: in.Tags, TimeRange: in.TimeRange, Near: in.Near}
	retrieveLimit := limit
	if managedCursor && s.cursor != nil {
		retrieveLimit++
	}
	req := rtsearch.BuildQueryFirstRequest(in.Query, in.ObjectTypes, retrieveLimit, filters, DefaultResultTargets)
	req.IDs = append([]string(nil), in.IDs...)
	req.Page.Offset = offset
	response, err := rtsearch.Retrieve(ctx, req, s.backend, viewer)
	if err != nil {
		return QueryExecution{}, err
	}
	response, hasMore := rtsearch.LimitResponse(response, limit)
	nextCursor := ""
	if hasMore {
		if !managedCursor || s.cursor == nil {
			return QueryExecution{}, ErrSearchCursor
		}
		nextCursor, err = s.cursor.encodeCursor(in, caller, identity, offset+len(response.Hits))
		if err != nil {
			return QueryExecution{}, err
		}
	}
	return QueryExecution{
		Response: response, InterpretedQuery: rtsearch.Analyze(in.Query, in.ObjectTypes), NextCursor: nextCursor,
	}, nil
}

func assistantRetrievalCaller(caller QueryCaller) bool {
	if strings.TrimSpace(caller.ServiceName) != "assistant-service" {
		return false
	}
	return callerHasScope(caller, "assistant.search.search_index_view.read")
}

func callerHasScope(caller QueryCaller, required string) bool {
	for _, scope := range caller.Scopes {
		if strings.TrimSpace(scope) == required {
			return true
		}
	}
	return false
}

func legacyPrincipalKey(viewer rtsearch.Viewer) string {
	if value := strings.TrimSpace(viewer.UserID); value != "" {
		return "viewer:" + value
	}
	return "legacy:anonymous"
}

func validateCloudObjectTypes(objectTypes []string) error {
	for _, raw := range objectTypes {
		switch rtsearch.Target(strings.ToLower(strings.TrimSpace(raw))) {
		case rtsearch.TargetArticle,
			rtsearch.TargetPhoto,
			rtsearch.TargetVideo,
			rtsearch.TargetUser,
			rtsearch.TargetEntity,
			rtsearch.TargetCircle,
			rtsearch.TargetGroup,
			rtsearch.TargetLocation:
		default:
			return fmt.Errorf("%w: unsupported cloud object type %q", ErrSearchInvalid, raw)
		}
	}
	return nil
}
