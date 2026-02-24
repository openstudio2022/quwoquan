package recommendation

import (
	"context"
	"fmt"
	"testing"
	"time"
)

func BenchmarkGetFeed_SingleSource(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	candidates := make([]ContentCandidate, 200)
	for i := range candidates {
		candidates[i] = ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			ContentType: []string{"image", "video", "article"}[i%3],
			AuthorID:    fmt.Sprintf("a%d", i%20),
			Tags:        []string{fmt.Sprintf("tag%d", i%10), fmt.Sprintf("cat%d", i%5)},
			PublishedAt: now.Add(-time.Duration(i) * time.Hour),
			LikeCount:   int64(200 - i),
			ViewCount:   int64(1000 - i*5),
		}
	}
	source := &mockCandidateSource{candidates: candidates}

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "bench", SessionID: "s1", ContentID: "seed",
		Action: "like", Tags: []string{"tag0", "tag1"},
	})

	engine := NewEngine(hp, []CandidateSource{source}, WithExploreFraction(0))

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		engine.GetFeed(ctx, GetFeedRequest{
			UserID:    "bench",
			SessionID: "s1",
			Limit:     20,
		})
	}
}

func BenchmarkGetFeed_WithSessionCache(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	candidates := make([]ContentCandidate, 200)
	for i := range candidates {
		candidates[i] = ContentCandidate{
			ContentID:   fmt.Sprintf("c%d", i),
			ContentType: []string{"image", "video", "article"}[i%3],
			AuthorID:    fmt.Sprintf("a%d", i%20),
			Tags:        []string{fmt.Sprintf("tag%d", i%10)},
			PublishedAt: now.Add(-time.Duration(i) * time.Hour),
			LikeCount:   int64(200 - i),
		}
	}
	source := &mockCandidateSource{candidates: candidates}

	hp.ProcessSignal(ctx, BehaviorSignal{
		UserID: "bench", SessionID: "s1", ContentID: "seed",
		Action: "like", Tags: []string{"tag0"},
	})

	cache := NewSessionCache(hp, 2*time.Second, 10000)
	engine := NewEngine(cache, []CandidateSource{source}, WithExploreFraction(0))

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		engine.GetFeed(ctx, GetFeedRequest{
			UserID:    "bench",
			SessionID: "s1",
			Limit:     20,
		})
	}
}

func BenchmarkGetFeed_MultiSource(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	now := time.Now()
	mkCandidates := func(prefix string, n int) []ContentCandidate {
		out := make([]ContentCandidate, n)
		for i := range out {
			out[i] = ContentCandidate{
				ContentID:   fmt.Sprintf("%s_%d", prefix, i),
				ContentType: "image",
				AuthorID:    fmt.Sprintf("a%d", i%10),
				Tags:        []string{fmt.Sprintf("tag%d", i%5)},
				PublishedAt: now,
				LikeCount:   int64(n - i),
				RecallPath:  prefix,
			}
		}
		return out
	}

	sources := []CandidateSource{
		&mockCandidateSource{candidates: mkCandidates("tag", 60)},
		&mockCandidateSource{candidates: mkCandidates("hot", 60)},
		&mockCandidateSource{candidates: mkCandidates("explore", 30)},
		&mockCandidateSource{candidates: mkCandidates("author", 30)},
	}

	cache := NewSessionCache(hp, 2*time.Second, 10000)
	engine := NewEngine(cache, sources, WithExploreFraction(0))

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		engine.GetFeed(ctx, GetFeedRequest{
			UserID:    "bench",
			SessionID: "s1",
			Limit:     20,
		})
	}
}

func BenchmarkHotPath_ProcessSignal(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		hp.ProcessSignal(ctx, BehaviorSignal{
			UserID:    "bench",
			SessionID: "s1",
			ContentID: fmt.Sprintf("c%d", i),
			Action:    "like",
			Tags:      []string{"tag1", "tag2"},
		})
	}
}

func BenchmarkHotPath_GetSessionState_Parallel(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	for i := 0; i < 100; i++ {
		hp.ProcessSignal(ctx, BehaviorSignal{
			UserID: "bench", SessionID: "s1",
			ContentID: fmt.Sprintf("c%d", i), Action: "click",
			Tags: []string{fmt.Sprintf("tag%d", i%10)},
		})
	}

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		hp.GetSessionState(ctx, "bench", "s1")
	}
}

func BenchmarkSessionCache_GetSessionState(b *testing.B) {
	redis := newMockRedis()
	hp := NewHotPath(redis)
	ctx := context.Background()

	for i := 0; i < 100; i++ {
		hp.ProcessSignal(ctx, BehaviorSignal{
			UserID: "bench", SessionID: "s1",
			ContentID: fmt.Sprintf("c%d", i), Action: "click",
			Tags: []string{fmt.Sprintf("tag%d", i%10)},
		})
	}

	cache := NewSessionCache(hp, 2*time.Second, 10000)

	b.ResetTimer()
	b.ReportAllocs()
	for i := 0; i < b.N; i++ {
		cache.GetSessionState(ctx, "bench", "s1")
	}
}
