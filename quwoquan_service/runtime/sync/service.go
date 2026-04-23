package runtimesync

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	defaultLimit       = 200
	maxLimit           = 500
	streamSeqKeyPrefix = "sync:user:"
	streamPatchPrefix  = "sync:user:"
	userRealtimePrefix = "rt:user:"
)

type Patch struct {
	SyncSeq    int64          `json:"syncSeq"`
	Type       string         `json:"type"`
	UserID     string         `json:"userId"`
	Payload    map[string]any `json:"payload"`
	OccurredAt time.Time      `json:"occurredAt"`
}

type PullResponse struct {
	Patches        []Patch `json:"patches"`
	LatestSyncSeq  int64   `json:"latestSyncSeq"`
	HasMore        bool    `json:"hasMore"`
	RequiresResync bool    `json:"requiresResync"`
}

type BatchAppendResult struct {
	Patches       []Patch  `json:"patches"`
	FailedUserIDs []string `json:"failedUserIds"`
}

type Option func(*Service)

type Service struct {
	dataClient rtredis.Client
	realtime   rtredis.Client
	patchTTL   time.Duration
	metrics    *MetricsCollector
}

func NewService(dataClient rtredis.Client, realtimeClient rtredis.Client, opts ...Option) *Service {
	service := &Service{
		dataClient: dataClient,
		realtime:   realtimeClient,
		patchTTL:   30 * 24 * time.Hour,
		metrics:    NewMetricsCollector(),
	}
	for _, opt := range opts {
		if opt != nil {
			opt(service)
		}
	}
	return service
}

func WithPatchTTL(ttl time.Duration) Option {
	return func(s *Service) {
		if s == nil || ttl <= 0 {
			return
		}
		s.patchTTL = ttl
	}
}

func WithMetricsCollector(collector *MetricsCollector) Option {
	return func(s *Service) {
		if s == nil || collector == nil {
			return
		}
		s.metrics = collector
	}
}

func (s *Service) MetricsSnapshot() map[string]float64 {
	if s == nil {
		return map[string]float64{}
	}
	return s.metrics.Snapshot()
}

func (s *Service) AppendPatch(
	ctx context.Context,
	userID string,
	patchType string,
	payload map[string]any,
) (Patch, error) {
	userID = strings.TrimSpace(userID)
	patchType = strings.TrimSpace(patchType)
	if userID == "" {
		return Patch{}, fmt.Errorf("sync userId is required")
	}
	if patchType == "" {
		return Patch{}, fmt.Errorf("sync patch type is required")
	}
	if s == nil || s.dataClient == nil {
		return Patch{}, fmt.Errorf("sync service is not configured")
	}
	seq, err := s.dataClient.Incr(ctx, s.seqKey(userID))
	if err != nil {
		return Patch{}, fmt.Errorf("allocate sync seq: %w", err)
	}
	patch := Patch{
		SyncSeq:    seq,
		Type:       patchType,
		UserID:     userID,
		Payload:    cloneMap(payload),
		OccurredAt: time.Now().UTC(),
	}
	body, err := json.Marshal(patch)
	if err != nil {
		return Patch{}, fmt.Errorf("marshal sync patch: %w", err)
	}
	if err := s.dataClient.SetBytes(ctx, s.patchKey(userID, seq), body, s.patchTTL); err != nil {
		return Patch{}, fmt.Errorf("store sync patch: %w", err)
	}
	if s.realtime != nil {
		_ = s.realtime.Publish(ctx, s.userChannel(userID), string(mustJSON(map[string]any{
			"type":          "sync_hint",
			"userId":        userID,
			"latestSyncSeq": seq,
		})))
	}
	s.metrics.RecordAppend(1)
	return patch, nil
}

func (s *Service) AppendPatchBatch(
	ctx context.Context,
	userIDs []string,
	patchType string,
	payload map[string]any,
) (BatchAppendResult, error) {
	patchType = strings.TrimSpace(patchType)
	if patchType == "" {
		return BatchAppendResult{}, fmt.Errorf("sync patch type is required")
	}
	if s == nil || s.dataClient == nil {
		return BatchAppendResult{}, fmt.Errorf("sync service is not configured")
	}
	normalizedUserIDs := dedupeUserIDs(userIDs)
	if len(normalizedUserIDs) == 0 {
		return BatchAppendResult{Patches: []Patch{}, FailedUserIDs: []string{}}, nil
	}
	pipe := s.dataClient.Pipeline(ctx)
	patches := make([]Patch, 0, len(normalizedUserIDs))
	failedUserIDs := make([]string, 0)
	storedUserIDs := make([]string, 0, len(normalizedUserIDs))
	for _, userID := range normalizedUserIDs {
		seq, err := s.dataClient.Incr(ctx, s.seqKey(userID))
		if err != nil {
			failedUserIDs = append(failedUserIDs, userID)
			continue
		}
		patch := Patch{
			SyncSeq:    seq,
			Type:       patchType,
			UserID:     userID,
			Payload:    cloneMap(payload),
			OccurredAt: time.Now().UTC(),
		}
		body, err := json.Marshal(patch)
		if err != nil {
			failedUserIDs = append(failedUserIDs, userID)
			continue
		}
		pipe.Set(ctx, s.patchKey(userID, seq), string(body), s.patchTTL)
		patches = append(patches, patch)
		storedUserIDs = append(storedUserIDs, userID)
	}
	if err := pipe.Exec(ctx); err != nil {
		return BatchAppendResult{
			Patches:       []Patch{},
			FailedUserIDs: normalizedUserIDs,
		}, fmt.Errorf("store sync patch batch: %w", err)
	}
	if s.realtime != nil {
		for _, patch := range patches {
			_ = s.realtime.Publish(ctx, s.userChannel(patch.UserID), string(mustJSON(map[string]any{
				"type":          "sync_hint",
				"userId":        patch.UserID,
				"latestSyncSeq": patch.SyncSeq,
			})))
		}
	}
	s.metrics.RecordAppendBatch(len(normalizedUserIDs), len(storedUserIDs))
	return BatchAppendResult{
		Patches:       patches,
		FailedUserIDs: failedUserIDs,
	}, nil
}

func (s *Service) Pull(
	ctx context.Context,
	userID string,
	afterSeq int64,
	limit int,
) (PullResponse, error) {
	start := time.Now()
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return PullResponse{}, fmt.Errorf("sync userId is required")
	}
	if s == nil || s.dataClient == nil {
		return PullResponse{}, fmt.Errorf("sync service is not configured")
	}
	if limit <= 0 {
		limit = defaultLimit
	}
	if limit > maxLimit {
		limit = maxLimit
	}
	latestSeq, err := s.LatestSeq(ctx, userID)
	if err != nil {
		return PullResponse{}, err
	}
	patches := make([]Patch, 0, limit)
	requiresResync := false
	upper := latestSeq
	if upper > afterSeq+int64(limit) {
		upper = afterSeq + int64(limit)
	}
	pipe := s.dataClient.Pipeline(ctx)
	results := make([]*rtredis.StringResult, 0, max(0, int(upper-afterSeq)))
	for seq := afterSeq + 1; seq <= upper; seq++ {
		results = append(results, pipe.Get(ctx, s.patchKey(userID, seq)))
	}
	if err := pipe.Exec(ctx); err != nil {
		s.metrics.RecordPull(time.Since(start), true)
		return PullResponse{}, fmt.Errorf("pull sync patches: %w", err)
	}
	for _, result := range results {
		raw, err := result.Result()
		if err != nil {
			requiresResync = true
			break
		}
		var patch Patch
		if err := json.Unmarshal([]byte(raw), &patch); err != nil {
			requiresResync = true
			break
		}
		patches = append(patches, patch)
	}
	sort.Slice(patches, func(i, j int) bool {
		return patches[i].SyncSeq < patches[j].SyncSeq
	})
	response := PullResponse{
		Patches:        patches,
		LatestSyncSeq:  latestSeq,
		HasMore:        !requiresResync && latestSeq > afterSeq+int64(len(patches)),
		RequiresResync: requiresResync,
	}
	s.metrics.RecordPull(time.Since(start), requiresResync)
	return response, nil
}

func (s *Service) LatestSeq(ctx context.Context, userID string) (int64, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return 0, nil
	}
	if s == nil || s.dataClient == nil {
		return 0, fmt.Errorf("sync service is not configured")
	}
	value, err := s.dataClient.Get(ctx, s.seqKey(userID))
	if err != nil {
		return 0, nil
	}
	var latest int64
	_, _ = fmt.Sscanf(value, "%d", &latest)
	return latest, nil
}

func (s *Service) seqKey(userID string) string {
	return streamSeqKeyPrefix + userID + ":latest"
}

func (s *Service) patchKey(userID string, seq int64) string {
	return fmt.Sprintf("%s%s:patch:%d", streamPatchPrefix, userID, seq)
}

func (s *Service) userChannel(userID string) string {
	return userRealtimePrefix + userID
}

func cloneMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}

func mustJSON(value map[string]any) []byte {
	body, _ := json.Marshal(value)
	return body
}

func dedupeUserIDs(userIDs []string) []string {
	if len(userIDs) == 0 {
		return []string{}
	}
	seen := make(map[string]struct{}, len(userIDs))
	out := make([]string, 0, len(userIDs))
	for _, userID := range userIDs {
		normalized := strings.TrimSpace(userID)
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	sort.Strings(out)
	return out
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}
