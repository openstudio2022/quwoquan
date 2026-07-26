package profileinteraction

import (
	"context"

	readfact "quwoquan_service/services/content-service/internal/content/profile_interaction_read_fact/application"
)

// Facades composes the activity projection query with the separate read-fact
// command object without merging their ownership.
type Facades struct {
	ActivityQueryFacade
	readfact.ReadFactAppendFacade
}

func BindFacades(query *ActivityQueryService, readFacts *readfact.ReadFactService) *Facades {
	if query == nil || readFacts == nil {
		return nil
	}
	return &Facades{ActivityQueryFacade: query, ReadFactAppendFacade: readFacts}
}

var _ interface {
	ListActivities(context.Context, ActivityPageQuery) (ActivityPage, error)
} = (*Facades)(nil)
