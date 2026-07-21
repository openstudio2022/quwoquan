package cache

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/circle-service/internal/application"
	circlemodel "quwoquan_service/services/circle-service/internal/domain/circle/model"
)

func TestCachedCircleDiscoveryFeedReaderIsolatesPersonaAndInvalidatesGeneration(t *testing.T) {
	t.Parallel()
	source := &circleDiscoveryFeedReaderSpy{}
	redis := rtredis.NewMemoryClient()
	reader := NewCachedCircleDiscoveryFeedReader(source, redis)
	ctx := context.Background()
	query := application.CircleDiscoveryFeedQuery{
		Scope:     application.CircleDiscoveryFeedScopeRecommended,
		Sort:      "recommended",
		Limit:     20,
		PersonaID: "persona-a",
	}

	first, err := reader.ListCircleDiscoveryFeed(ctx, query)
	if err != nil {
		t.Fatalf("first read: %v", err)
	}
	second, err := reader.ListCircleDiscoveryFeed(ctx, query)
	if err != nil {
		t.Fatalf("cache read: %v", err)
	}
	if source.calls != 1 || len(first.Circles) != 1 || len(second.Circles) != 1 {
		t.Fatalf("same persona should read the cached typed slice once, calls=%d first=%+v second=%+v", source.calls, first, second)
	}

	query.PersonaID = "persona-b"
	if _, err := reader.ListCircleDiscoveryFeed(ctx, query); err != nil {
		t.Fatalf("different persona read: %v", err)
	}
	if source.calls != 2 {
		t.Fatalf("persona-scoped cache must not share slices, calls=%d", source.calls)
	}

	if err := InvalidateCircleDiscoveryFeed(ctx, redis); err != nil {
		t.Fatalf("invalidate generation: %v", err)
	}
	query.PersonaID = "persona-a"
	if _, err := reader.ListCircleDiscoveryFeed(ctx, query); err != nil {
		t.Fatalf("read after invalidation: %v", err)
	}
	if source.calls != 3 {
		t.Fatalf("generation invalidation must bypass prior slices, calls=%d", source.calls)
	}
}

type circleDiscoveryFeedReaderSpy struct {
	calls int
}

func (spy *circleDiscoveryFeedReaderSpy) ListCircleDiscoveryFeed(
	_ context.Context,
	_ application.CircleDiscoveryFeedQuery,
) (application.CircleDiscoveryFeedSlice, error) {
	spy.calls++
	return application.CircleDiscoveryFeedSlice{
		Circles: []circlemodel.Circle{{ID: "circle-1", Name: "cache contract"}},
		Items:   []application.CircleFeedPost{},
	}, nil
}
