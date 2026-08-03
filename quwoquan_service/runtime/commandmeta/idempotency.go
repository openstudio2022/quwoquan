package commandmeta

import (
	"context"
	"strings"

	"quwoquan_service/runtime/operation"
)

type idempotencyKeyContextKey struct{}

func WithIdempotencyKey(ctx context.Context, key string) context.Context {
	return context.WithValue(ctx, idempotencyKeyContextKey{}, strings.TrimSpace(key))
}

func IdempotencyKey(ctx context.Context) string {
	value, _ := ctx.Value(idempotencyKeyContextKey{}).(string)
	if normalized := strings.TrimSpace(value); normalized != "" {
		return normalized
	}
	if current, ok := operation.FromContext(ctx); ok {
		return strings.TrimSpace(current.IdempotencyKey)
	}
	return ""
}
