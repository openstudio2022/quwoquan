package feed

import postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"

const (
	DefaultFeedPageSize = postports.DefaultPostQueryPageSize
	MaxFeedPageSize     = postports.MaxPostQueryPageSize
)

// NormalizeFeedLimit is the single application boundary for every feed route.
// Recall fanout, hydration and explicit Post reads must all derive their work
// from this bounded value rather than the untrusted wire query parameter.
func NormalizeFeedLimit(raw int) int {
	switch {
	case raw <= 0:
		return DefaultFeedPageSize
	case raw > MaxFeedPageSize:
		return MaxFeedPageSize
	default:
		return raw
	}
}
