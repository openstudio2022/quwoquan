package filtercatalogrelease

import (
	"context"
	"strings"
)

type filterCatalogIdempotencyContextKey struct{}

func WithIdempotencyKey(ctx context.Context, key string) context.Context {
	return context.WithValue(
		ctx,
		filterCatalogIdempotencyContextKey{},
		strings.TrimSpace(key),
	)
}

func idempotencyKey(ctx context.Context) string {
	key, _ := ctx.Value(filterCatalogIdempotencyContextKey{}).(string)
	return strings.TrimSpace(key)
}
