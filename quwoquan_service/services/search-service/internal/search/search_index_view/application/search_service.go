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

// SearchService runs the canonical search(request) over the injected backend.
type SearchService struct {
	backend rtsearch.RecallBackend
}

// NewSearchService builds the query use case.
func NewSearchService(backend rtsearch.RecallBackend) *SearchService {
	return &SearchService{backend: backend}
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
	Near *rtsearch.GeoNear
}

// Search runs the unified retrieve over the backend, mapping the query-first
// input into the frozen RetrieveRequest contract (single-sourced in runtime).
func (s *SearchService) Search(ctx context.Context, in QueryInput, viewer rtsearch.Viewer) (rtsearch.RetrieveResponse, error) {
	if err := validateCloudObjectTypes(in.ObjectTypes); err != nil {
		return rtsearch.RetrieveResponse{}, err
	}
	limit := in.Limit
	if limit <= 0 {
		if strings.EqualFold(in.Mode, "suggest") {
			limit = SuggestLimit
		} else {
			limit = ResultLimit
		}
	}
	filters := rtsearch.RetrieveFilters{Tags: in.Tags, TimeRange: in.TimeRange, Near: in.Near}
	req := rtsearch.BuildQueryFirstRequest(in.Query, in.ObjectTypes, limit, filters, DefaultResultTargets)
	req.IDs = append([]string(nil), in.IDs...)
	return rtsearch.Retrieve(ctx, req, s.backend, viewer)
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
