package commandmeta

import (
	"context"
	"strings"
)

type idempotencyKeyContextKey struct{}

func WithIdempotencyKey(ctx context.Context, key string) context.Context {
	return context.WithValue(ctx, idempotencyKeyContextKey{}, strings.TrimSpace(key))
}

func IdempotencyKey(ctx context.Context) string {
	value, _ := ctx.Value(idempotencyKeyContextKey{}).(string)
	return strings.TrimSpace(value)
}
