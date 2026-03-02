package recommendation

import (
	"context"
	"sort"
	"time"
)

// PreRanker applies a lightweight filter before full model scoring.
// TikTok-style architecture: recall produces O(1000) candidates,
// pre-ranker reduces to O(200), then full scorer handles O(200).
type PreRanker interface {
	PreRank(ctx context.Context, candidates []ContentCandidate, limit int) []ContentCandidate
}

// NullPreRanker passes all candidates through (no pre-ranking).
type NullPreRanker struct{}

func (*NullPreRanker) PreRank(_ context.Context, candidates []ContentCandidate, _ int) []ContentCandidate {
	return candidates
}

// QualityPreRanker is a lightweight pre-ranker that:
// 1. Removes stale content beyond MaxAge
// 2. Applies a cheap quality heuristic (engagement density)
// 3. Truncates to limit
//
// This avoids sending hundreds of low-quality candidates to the
// expensive full scorer (ML or rule-based).
type QualityPreRanker struct {
	MaxAge time.Duration
}

func NewQualityPreRanker(maxAge time.Duration) *QualityPreRanker {
	if maxAge <= 0 {
		maxAge = 7 * 24 * time.Hour
	}
	return &QualityPreRanker{MaxAge: maxAge}
}

func (p *QualityPreRanker) PreRank(_ context.Context, candidates []ContentCandidate, limit int) []ContentCandidate {
	if limit <= 0 {
		limit = 200
	}

	now := time.Now()
	cutoff := now.Add(-p.MaxAge)

	// Phase 1: filter out stale content
	alive := make([]ContentCandidate, 0, len(candidates))
	for _, c := range candidates {
		if !c.PublishedAt.IsZero() && c.PublishedAt.Before(cutoff) {
			continue
		}
		alive = append(alive, c)
	}

	if len(alive) <= limit {
		return alive
	}

	// Phase 2: cheap quality score (engagement density) for truncation
	type ranked struct {
		idx   int
		score float64
	}
	items := make([]ranked, len(alive))
	for i, c := range alive {
		engagement := float64(c.LikeCount) + float64(c.CommentCount)*2 + float64(c.ShareCount)*3
		views := float64(c.ViewCount)
		var density float64
		if views > 0 {
			density = engagement / views
		} else {
			density = engagement * 0.01
		}

		// Fresh content gets a boost to prevent cold-start penalization
		ageHours := now.Sub(c.PublishedAt).Hours()
		if ageHours < 0 {
			ageHours = 0
		}
		freshBoost := 1.0
		if ageHours < 6 {
			freshBoost = 2.0
		} else if ageHours < 24 {
			freshBoost = 1.5
		}

		items[i] = ranked{idx: i, score: density * freshBoost}
	}

	sort.Slice(items, func(i, j int) bool {
		if items[i].score != items[j].score {
			return items[i].score > items[j].score
		}
		return items[i].idx < items[j].idx
	})

	result := make([]ContentCandidate, 0, limit)
	for i := 0; i < limit && i < len(items); i++ {
		result = append(result, alive[items[i].idx])
	}
	return result
}

// EmbeddingService generates vector embeddings from text.
// Used by vector recall and potentially by model scoring for semantic features.
type EmbeddingService interface {
	Embed(ctx context.Context, text string) ([]float64, error)
	EmbedBatch(ctx context.Context, texts []string) ([][]float64, error)
}
