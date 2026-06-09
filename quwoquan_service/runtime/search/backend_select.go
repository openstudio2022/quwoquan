package search

import (
	"context"
	"os"
	"strings"
)

// BackendMode selects the active recall backend.
type BackendMode string

const (
	BackendNative BackendMode = "native"
	BackendES     BackendMode = "es"
)

// ResolveBackendMode picks the backend from config/env. Default is native; ES is
// only chosen when explicitly requested AND an endpoint is injected. Selection
// is transparent to the retrieve contract and all callers.
func ResolveBackendMode() BackendMode {
	mode := strings.ToLower(strings.TrimSpace(os.Getenv("SEARCH_BACKEND")))
	switch mode {
	case string(BackendES):
		if strings.TrimSpace(os.Getenv("ES_ENDPOINT")) != "" {
			return BackendES
		}
		return BackendNative
	case string(BackendNative), "":
		return BackendNative
	default:
		return BackendNative
	}
}

// FallbackBackend wraps a primary backend and falls back to a secondary backend
// when the primary errors. Used to keep ES failures from breaking the main path
// (degrade to native).
type FallbackBackend struct {
	Primary  RecallBackend
	Fallback RecallBackend
}

// Name implements RecallBackend.
func (b FallbackBackend) Name() string {
	if b.Primary != nil {
		return b.Primary.Name()
	}
	if b.Fallback != nil {
		return b.Fallback.Name()
	}
	return "native_store"
}

// Recall tries the primary, then the fallback on error.
func (b FallbackBackend) Recall(ctx context.Context, plan RetrievePlan) ([]RecallCandidate, error) {
	if b.Primary != nil {
		if cands, err := b.Primary.Recall(ctx, plan); err == nil {
			return cands, nil
		}
	}
	if b.Fallback != nil {
		return b.Fallback.Recall(ctx, plan)
	}
	return nil, nil
}
