package recommendation

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

const (
	RecallPathCollaborativeI2I = "collab_i2i"
	RecallPathCollaborativeU2I = "collab_u2i"
)

// CollaborativeCandidateStore reads already-materialized itemCF/Swing/u2i
// candidates. Implementations must not compute co-occurrence on the feed read
// path; offline jobs own materialization and replay evaluation.
type CollaborativeCandidateStore interface {
	GetI2ICandidates(ctx context.Context, seedContentIDs []string, limit int) ([]ContentCandidate, error)
	GetU2ICandidates(ctx context.Context, userID string, limit int) ([]ContentCandidate, error)
}

type NullCollaborativeCandidateStore struct{}

func (*NullCollaborativeCandidateStore) GetI2ICandidates(context.Context, []string, int) ([]ContentCandidate, error) {
	return nil, nil
}

func (*NullCollaborativeCandidateStore) GetU2ICandidates(context.Context, string, int) ([]ContentCandidate, error) {
	return nil, nil
}

type CollaborativeRecallSource struct {
	store            CollaborativeCandidateStore
	enabled          bool
	maxI2ICandidates int
	maxU2ICandidates int
	quotaPct         int
}

type CollaborativeRecallConfig struct {
	Enabled          bool
	MaxI2ICandidates int
	MaxU2ICandidates int
	QuotaPct         int
}

func NewCollaborativeRecallSource(store CollaborativeCandidateStore, cfg CollaborativeRecallConfig) *CollaborativeRecallSource {
	if store == nil {
		store = &NullCollaborativeCandidateStore{}
	}
	return &CollaborativeRecallSource{
		store:            store,
		enabled:          cfg.Enabled,
		maxI2ICandidates: cfg.MaxI2ICandidates,
		maxU2ICandidates: cfg.MaxU2ICandidates,
		quotaPct:         cfg.QuotaPct,
	}
}

func (s *CollaborativeRecallSource) Recall(ctx context.Context, req RecallRequest) ([]ContentCandidate, error) {
	if s == nil || !s.enabled {
		return nil, SkipRecall("collaborative recall is disabled")
	}
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	quota := limit * s.quotaPct / 100
	if quota <= 0 {
		quota = 1
	}

	i2iLimit := minPositive(s.maxI2ICandidates, quota)
	if s.maxU2ICandidates > 0 && i2iLimit >= quota && quota > 1 {
		i2iLimit = quota / 2
	}

	var out []ContentCandidate
	var recallErrs []error
	seen := map[string]struct{}{}
	if i2iLimit > 0 {
		i2i, err := s.store.GetI2ICandidates(ctx, collaborativeSeedIDs(req), i2iLimit*2)
		if err == nil {
			i2i = filterCollaborativeVertical(i2i, req.Vertical)
			appendCollaborative(&out, seen, i2i, RecallPathCollaborativeI2I, quota, i2iLimit)
		} else {
			recallErrs = append(recallErrs, fmt.Errorf("collaborative i2i recall: %w", err))
		}
	}
	if len(out) < quota && s.maxU2ICandidates > 0 {
		u2iLimit := minPositive(s.maxU2ICandidates, quota-len(out))
		u2i, err := s.store.GetU2ICandidates(ctx, req.UserID, u2iLimit*2)
		if err == nil {
			u2i = filterCollaborativeVertical(u2i, req.Vertical)
			appendCollaborative(&out, seen, u2i, RecallPathCollaborativeU2I, quota, u2iLimit)
		} else {
			recallErrs = append(recallErrs, fmt.Errorf("collaborative u2i recall: %w", err))
		}
	}
	if len(out) > quota {
		out = out[:quota]
	}
	return out, errors.Join(recallErrs...)
}

func collaborativeSeedIDs(req RecallRequest) []string {
	seeds := make([]string, 0, len(req.SeedContentIDs)+2)
	for _, raw := range req.SeedContentIDs {
		if raw != "" {
			seeds = append(seeds, raw)
		}
	}
	for _, raw := range []string{req.HomepageID, req.TopicID} {
		if raw != "" {
			seeds = append(seeds, raw)
		}
	}
	return seeds
}

func appendCollaborative(out *[]ContentCandidate, seen map[string]struct{}, items []ContentCandidate, path string, totalLimit int, pathLimit int) {
	added := 0
	for _, c := range items {
		if len(*out) >= totalLimit || added >= pathLimit {
			return
		}
		if c.ContentID == "" {
			continue
		}
		if _, ok := seen[c.ContentID]; ok {
			continue
		}
		c.RecallPath = path
		seen[c.ContentID] = struct{}{}
		*out = append(*out, c)
		added++
	}
}

func filterCollaborativeVertical(items []ContentCandidate, vertical string) []ContentCandidate {
	vertical = normalizeRecallVertical(vertical)
	if vertical == "" || len(items) == 0 {
		return items
	}
	out := items[:0]
	for _, item := range items {
		if normalizeRecallVertical(item.ContentVertical) == vertical {
			out = append(out, item)
		}
	}
	return out
}

func normalizeRecallVertical(raw string) string {
	switch strings.TrimSpace(strings.ToLower(raw)) {
	case "", "all", "home", "discovery":
		return ""
	case "travel", "travel_photography", "旅行", "旅游":
		return "travel_photography"
	default:
		return strings.TrimSpace(strings.ToLower(raw))
	}
}

func minPositive(value int, cap int) int {
	if cap <= 0 {
		return 0
	}
	if value <= 0 || value > cap {
		return cap
	}
	return value
}
