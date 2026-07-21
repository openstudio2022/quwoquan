package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/application"
)

const (
	circleDiscoveryFeedCacheKeyPrefix = "cache:circle-discovery:"
	circleDiscoveryFeedGenerationKey  = circleDiscoveryFeedCacheKeyPrefix + "generation"
	circleDiscoveryFeedCacheTTL       = 60 * time.Second
)

// CachedCircleDiscoveryFeedReader keeps discovery slices isolated by actor
// scope while a generation key makes every source-fact invalidation atomic.
// The cached payload is a typed application slice, never an untyped wire map.
type CachedCircleDiscoveryFeedReader struct {
	source application.CircleDiscoveryFeedReader
	rdb    rtredis.Client
}

var _ application.CircleDiscoveryFeedReader = (*CachedCircleDiscoveryFeedReader)(nil)

func NewCachedCircleDiscoveryFeedReader(
	source application.CircleDiscoveryFeedReader,
	rdb rtredis.Client,
) *CachedCircleDiscoveryFeedReader {
	if source == nil || rdb == nil {
		panic("cached circle discovery feed reader requires source and redis")
	}
	return &CachedCircleDiscoveryFeedReader{source: source, rdb: rdb}
}

func (reader *CachedCircleDiscoveryFeedReader) ListCircleDiscoveryFeed(
	ctx context.Context,
	query application.CircleDiscoveryFeedQuery,
) (application.CircleDiscoveryFeedSlice, error) {
	generation := reader.generation(ctx)
	key, err := circleDiscoveryFeedCacheKey(generation, query)
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, err
	}
	if payload, readErr := reader.rdb.GetBytes(ctx, key); readErr == nil {
		var cached application.CircleDiscoveryFeedSlice
		if json.Unmarshal(payload, &cached) == nil {
			return cached, nil
		}
	}

	result, err := reader.source.ListCircleDiscoveryFeed(ctx, query)
	if err != nil {
		return application.CircleDiscoveryFeedSlice{}, err
	}
	if payload, marshalErr := json.Marshal(result); marshalErr == nil {
		// Cache unavailability is not a read-path fallback: source success stays
		// successful, while Redis failure remains observable through its adapter.
		_ = reader.rdb.SetBytes(ctx, key, payload, circleDiscoveryFeedCacheTTL)
	}
	return result, nil
}

func (reader *CachedCircleDiscoveryFeedReader) generation(ctx context.Context) string {
	generation, err := reader.rdb.Get(ctx, circleDiscoveryFeedGenerationKey)
	if err != nil || strings.TrimSpace(generation) == "" {
		return "0"
	}
	return generation
}

// InvalidateCircleDiscoveryFeed advances the namespace generation instead of
// scanning Redis. It invalidates every persona/scope/category cursor slice
// without retaining a second cache-key registry.
func InvalidateCircleDiscoveryFeed(ctx context.Context, rdb rtredis.Client) error {
	if rdb == nil {
		return fmt.Errorf("circle discovery cache invalidator requires redis")
	}
	if _, err := rdb.Incr(ctx, circleDiscoveryFeedGenerationKey); err != nil {
		return fmt.Errorf("advance circle discovery cache generation: %w", err)
	}
	return nil
}

func circleDiscoveryFeedCacheKey(
	generation string,
	query application.CircleDiscoveryFeedQuery,
) (string, error) {
	personaHash := sha256.Sum256([]byte(strings.TrimSpace(query.PersonaID)))
	payload, err := json.Marshal(struct {
		Generation  string `json:"generation"`
		Scope       string `json:"scope"`
		PersonaHash string `json:"personaHash"`
		Category    string `json:"category"`
		SubCategory string `json:"subCategory"`
		Sort        string `json:"sort"`
		Cursor      string `json:"cursor"`
		Limit       int    `json:"limit"`
	}{
		Generation:  strings.TrimSpace(generation),
		Scope:       string(query.Scope),
		PersonaHash: hex.EncodeToString(personaHash[:]),
		Category:    strings.TrimSpace(query.Category),
		SubCategory: strings.TrimSpace(query.SubCategory),
		Sort:        strings.TrimSpace(query.Sort),
		Cursor:      strings.TrimSpace(query.Cursor),
		Limit:       query.Limit,
	})
	if err != nil {
		return "", fmt.Errorf("encode circle discovery cache key: %w", err)
	}
	sum := sha256.Sum256(payload)
	return circleDiscoveryFeedCacheKeyPrefix + hex.EncodeToString(sum[:]), nil
}
