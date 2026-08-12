package owner

import (
	"context"
	"errors"

	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/application"
	"quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/domain"
)

// QueryExecutorRouter is the closed API Edge composition for signed owner
// Query Slices. It never falls through to an arbitrary URL, query text, or a
// generic REST proxy when an executor key is absent.
type QueryExecutorRouter struct {
	contentPost *ContentPostQueryExecutor
	searchPage  *SearchPageQueryExecutor
}

func NewQueryExecutorRouter(
	contentPost *ContentPostQueryExecutor,
	searchPage *SearchPageQueryExecutor,
) (*QueryExecutorRouter, error) {
	if contentPost == nil || searchPage == nil {
		return nil, errors.New("all signed GraphQL owner executors are required")
	}
	return &QueryExecutorRouter{contentPost: contentPost, searchPage: searchPage}, nil
}

func (router *QueryExecutorRouter) Execute(
	ctx context.Context,
	entry domain.Entry,
	variables map[string]any,
) (application.ExecutionResult, error) {
	if router == nil {
		return application.ExecutionResult{}, errors.New("GraphQL owner executor router is nil")
	}
	switch entry.ExecutorKey {
	case contentPostExecutorKey:
		return router.contentPost.Execute(ctx, entry, variables)
	case searchPageExecutorKey:
		return router.searchPage.Execute(ctx, entry, variables)
	default:
		return application.ExecutionResult{}, errors.New("signed GraphQL executor key has no runtime binding")
	}
}

func ValidateExecutableEntry(entry domain.Entry) error {
	switch entry.ExecutorKey {
	case contentPostExecutorKey:
		return ValidateContentPostBundleEntry(entry)
	case searchPageExecutorKey:
		return ValidateSearchPageEntry(entry)
	default:
		return errors.New("signed GraphQL executor key has no composition binding")
	}
}
