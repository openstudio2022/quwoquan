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

// MaxCursorOffset bounds pagination depth (search_slo.yaml cost guard
// no_deep_paging): recall cost grows linearly with the decoded offset, and no
// commercial search journey needs unbounded depth. Reaching the bound simply
// stops issuing nextCursor so the client terminates pagination cleanly.
const MaxCursorOffset = 200

var ErrSearchInvalid = errors.New("invalid search request")

var ErrSearchForbidden = errors.New("search mode is forbidden for caller")

// PaginationSnapshots is the owner port over the recall engine's point-in-time
// capability (es.Client implements it). Snapshots are opened lazily on the
// first follow-up page and renewed per page, so only actively-paging users
// hold segment references.
type PaginationSnapshots interface {
	OpenPIT(ctx context.Context) (string, error)
	ClosePIT(ctx context.Context, id string) error
}

// SearchService runs the canonical search(request) over the injected backend.
type SearchService struct {
	backend   rtsearch.RecallBackend
	cursor    *SearchCursorCodec
	snapshots PaginationSnapshots
}

type SearchServiceOption func(*SearchService)

func WithSearchCursorCodec(codec *SearchCursorCodec) SearchServiceOption {
	return func(service *SearchService) { service.cursor = codec }
}

// WithPaginationSnapshots enables PIT-backed pagination snapshots. Without it
// pagination stays offset-only (test/native backends).
func WithPaginationSnapshots(snapshots PaginationSnapshots) SearchServiceOption {
	return func(service *SearchService) { service.snapshots = snapshots }
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
// ObjectTypes carries canonical object vocabulary (content.post/user.profile/
// entity.homepage/circle.circle/circle.group/location.place); ContentTypes
// narrows the content.post family (article/image/video). Internal recall
// targets never appear on this input.
type QueryInput struct {
	Query        string
	Mode         string
	ObjectTypes  []string
	ContentTypes []string
	IDs          []string
	Limit        int
	Tags         []string
	TimeRange    *rtsearch.TimeRange
	// Near is the optional 附近 geo radius filter; it spans every target that
	// carries a Geo dimension (entity/content today, user/circle next).
	Near   *rtsearch.GeoNear
	Cursor string
	// BoostTerms carry the AB-assigned query-time score lifts (term_heat arm);
	// they enter the engine query so ranking stays single-sourced in recall.
	BoostTerms []rtsearch.BoostTerm
	// ReplicaPreference pins recall to a deterministic replica per subject so
	// repeated identical queries never jitter across replica segment-merge
	// differences (must be a non-PII digest; derived from the subject key).
	ReplicaPreference string
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
	targets, err := rtsearch.TargetsForCanonicalFilter(in.ObjectTypes, in.ContentTypes, DefaultResultTargets)
	if err != nil {
		return QueryExecution{}, fmt.Errorf("%w: %s", ErrSearchInvalid, err.Error())
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
	pitID := ""
	if cursor := strings.TrimSpace(in.Cursor); cursor != "" {
		if !managedCursor || s.cursor == nil {
			return QueryExecution{}, ErrSearchCursor
		}
		decodedOffset, decodedPIT, err := s.cursor.decodeCursor(cursor, in, caller, identity)
		if err != nil {
			return QueryExecution{}, err
		}
		offset = decodedOffset
		pitID = decodedPIT
	}
	// Lazy pagination snapshot: the first follow-up page opens the PIT so every
	// later page reads the exact index state this pagination started on. First
	// pages never pay for a snapshot (most searches are never paged).
	if offset > 0 && pitID == "" && s.snapshots != nil {
		opened, err := s.snapshots.OpenPIT(ctx)
		if err != nil {
			return QueryExecution{}, err
		}
		pitID = opened
	}
	filters := rtsearch.RetrieveFilters{Tags: in.Tags, TimeRange: in.TimeRange, Near: in.Near}
	retrieveLimit := limit
	if managedCursor && s.cursor != nil {
		retrieveLimit++
	}
	req := rtsearch.RetrieveRequest{
		Targets:    targets,
		Terms:      rtsearch.SplitQueryTerms(in.Query),
		Filters:    filters,
		Page:       rtsearch.PageRequest{Limit: retrieveLimit},
		BoostTerms: in.BoostTerms,

		ReplicaPreference: in.ReplicaPreference,
		PITID:             pitID,
	}
	req.IDs = append([]string(nil), in.IDs...)
	req.Page.Offset = offset
	response, err := rtsearch.Retrieve(ctx, req, s.backend, viewer)
	if err != nil {
		if errors.Is(err, rtsearch.ErrPaginationSnapshotInvalid) {
			// The snapshot this cursor was bound to is gone: fail the cursor
			// closed so the caller restarts from a fresh first page instead of
			// silently reading an unsnapshotted index state.
			return QueryExecution{}, ErrSearchCursor
		}
		return QueryExecution{}, err
	}
	response, hasMore := rtsearch.LimitResponse(response, limit)
	nextCursor := ""
	if hasMore && offset+len(response.Hits) < MaxCursorOffset {
		if !managedCursor || s.cursor == nil {
			return QueryExecution{}, ErrSearchCursor
		}
		nextCursor, err = s.cursor.encodeCursor(in, caller, identity, offset+len(response.Hits), pitID)
		if err != nil {
			return QueryExecution{}, err
		}
	} else if pitID != "" && s.snapshots != nil {
		// Pagination reached its end: release the snapshot eagerly instead of
		// waiting for the keep_alive to lapse (best-effort).
		_ = s.snapshots.ClosePIT(ctx, pitID)
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
