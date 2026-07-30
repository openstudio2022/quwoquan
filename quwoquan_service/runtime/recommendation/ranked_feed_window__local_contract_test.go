// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package recommendation

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/boundedrecord"
)

type rankedWindowCountingSource struct {
	mu         sync.Mutex
	calls      int
	candidates []ContentCandidate
}

func (s *rankedWindowCountingSource) Recall(
	_ context.Context,
	_ RecallRequest,
) ([]ContentCandidate, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.calls++
	return append([]ContentCandidate(nil), s.candidates...), nil
}

func (s *rankedWindowCountingSource) replace(candidates []ContentCandidate) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.candidates = append([]ContentCandidate(nil), candidates...)
}

func (s *rankedWindowCountingSource) callCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.calls
}

type rankedWindowCountingScorer struct {
	mu    sync.Mutex
	calls int
}

func (s *rankedWindowCountingScorer) ScoreBatch(
	_ context.Context,
	_ *ScoringFeatures,
	candidates []ContentCandidate,
) ([]ScoredCandidate, error) {
	s.mu.Lock()
	s.calls++
	s.mu.Unlock()
	scored := make([]ScoredCandidate, 0, len(candidates))
	for index, candidate := range candidates {
		scored = append(scored, ScoredCandidate{
			Candidate: candidate,
			Score:     float64(len(candidates) - index),
		})
	}
	return scored, nil
}

func (s *rankedWindowCountingScorer) callCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.calls
}

func TestRankedFeedWindowContinuationNeverRecomputesLiveRanking(t *testing.T) {
	const (
		releaseID = "rel_ranked_window"
		digest    = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	)
	candidates := make([]ContentCandidate, 0, 6)
	for index := 0; index < 6; index++ {
		contentType := "image"
		if index%2 == 1 {
			contentType = "video"
		}
		candidates = append(candidates, ContentCandidate{
			ContentID: fmt.Sprintf("post-ranked-%d", index), ContentType: contentType,
			AuthorID:    fmt.Sprintf("author-ranked-%d", index),
			SourceOwner: "qwq_data", SupplySource: "data_engineering",
			ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active",
		})
	}
	redis := newMockRedis()
	source := &rankedWindowCountingSource{candidates: candidates}
	scorer := &rankedWindowCountingScorer{}
	engine := NewEngine(
		NewHotPath(redis),
		[]CandidateSource{source},
		WithScorer(scorer),
		WithPolicyStore(noExplorePolicyStore()),
	)
	request := GetFeedRequest{
		UserID: "actor-ranked", PersonaID: "persona-ranked", SessionID: "session-ranked",
		RankedWindowSubjectID: "actor\x00actor-ranked",
		FeedType:              FeedDiscovery, Sort: FeedSortRecommend, Surface: "home", ChannelID: "recommend",
		FeedRequestID: "frq_ranked_window", ActiveReleaseID: releaseID,
		ActiveManifestDigest: digest, Limit: 2, DeferDeliveryAccounting: true,
	}
	first, err := engine.GetFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("initial ranked page: %v", err)
	}
	if first.NextContinuation == nil {
		t.Fatalf("initial page did not persist a ranked window: %+v", first)
	}
	window, err := engine.rankedWindows.Load(
		context.Background(),
		request.RankedWindowSubjectID,
		first.NextContinuation.WindowID,
	)
	if err != nil {
		t.Fatalf("load persisted ranked window: %v", err)
	}
	if got := window.ExpiresAt.Sub(window.CreatedAt); got != RankedFeedWindowTTL {
		t.Fatalf("window TTL = %v, want %v", got, RankedFeedWindowTTL)
	}
	if len(window.Items) > RankedFeedWindowMaxItems {
		t.Fatalf("window items = %d, max = %d", len(window.Items), RankedFeedWindowMaxItems)
	}
	for index, item := range window.Items {
		if item.Ordinal != index+1 || item.Item.ContentID == "" {
			t.Fatalf("invalid total order at %d: %+v", index, item)
		}
	}
	if window.Provenance.CandidateWatermark == "" || window.Provenance.PolicyDigest == "" ||
		window.Provenance.FeatureSnapshotAt == "" ||
		window.Provenance.ScorerPath == "" {
		t.Fatalf("window provenance binding incomplete: %+v", window.Provenance)
	}

	// Make a live recomputation observably wrong. A valid continuation must not
	// touch either source or scorer and must return the stored ordinal slice.
	source.replace([]ContentCandidate{{
		ContentID: "post-live-forbidden", ContentType: "article",
		AuthorID: "author-live", SourceOwner: "qwq_data", SupplySource: "data_engineering",
		ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active",
	}})
	request.Continuation = first.NextContinuation
	second, err := engine.GetFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("continue immutable ranked window: %v", err)
	}
	if source.callCount() != 1 || scorer.callCount() != 1 {
		t.Fatalf("continuation recomputed live ranking: source=%d scorer=%d", source.callCount(), scorer.callCount())
	}
	wantEntries := window.Items[2:4]
	if len(second.Items) != len(wantEntries) {
		t.Fatalf("continuation item count = %d, want %d", len(second.Items), len(wantEntries))
	}
	for index, item := range second.Items {
		if item.ContentID != wantEntries[index].Item.ContentID || item.rank != wantEntries[index].Ordinal {
			t.Fatalf("continuation[%d] = (%s,%d), want (%s,%d)", index, item.ContentID, item.rank, wantEntries[index].Item.ContentID, wantEntries[index].Ordinal)
		}
	}
}

func TestRankedFeedWindowContinuationBindingAndAnchorFailClosed(t *testing.T) {
	engine, request, continuation := newRankedWindowContinuationFixture(t)
	tests := []struct {
		name   string
		mutate func(*GetFeedRequest)
	}{
		{name: "actor", mutate: func(req *GetFeedRequest) { req.UserID = "other-actor" }},
		{name: "persona", mutate: func(req *GetFeedRequest) { req.PersonaID = "other-persona" }},
		{name: "session", mutate: func(req *GetFeedRequest) { req.SessionID = "other-session" }},
		{name: "route", mutate: func(req *GetFeedRequest) { req.ChannelID = "travel" }},
		{name: "feed request", mutate: func(req *GetFeedRequest) { req.FeedRequestID = "frq_other" }},
		{name: "release", mutate: func(req *GetFeedRequest) { req.ActiveReleaseID = "rel_other" }},
		{name: "digest", mutate: func(req *GetFeedRequest) {
			req.ActiveManifestDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
		}},
		{name: "anchor content", mutate: func(req *GetFeedRequest) { req.Continuation.AfterContentID = "post_tampered" }},
		{name: "anchor ordinal", mutate: func(req *GetFeedRequest) { req.Continuation.AfterOrdinal = 999 }},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			candidate := request
			copiedContinuation := *continuation
			candidate.Continuation = &copiedContinuation
			test.mutate(&candidate)
			_, err := engine.GetFeed(context.Background(), candidate)
			if !errors.Is(err, ErrInvalidFeedCursor) {
				t.Fatalf("error = %v, want ErrInvalidFeedCursor", err)
			}
		})
	}
}

type failingRankedFeedWindowStore struct{}

func (failingRankedFeedWindowStore) Create(
	context.Context,
	rankedFeedWindow,
) (rankedFeedWindow, error) {
	return rankedFeedWindow{}, ErrRankedFeedWindowStoreUnavailable
}

func (failingRankedFeedWindowStore) Load(
	context.Context,
	string,
	string,
) (rankedFeedWindow, error) {
	return rankedFeedWindow{}, ErrRankedFeedWindowStoreUnavailable
}

func TestRankedFeedWindowCreateFailureNeverIssuesContinuation(t *testing.T) {
	engine, request, _ := newRankedWindowContinuationFixture(t)
	engine.rankedWindows = failingRankedFeedWindowStore{}
	request.Limit = 1
	response, err := engine.GetFeed(context.Background(), request)
	if err != nil {
		t.Fatalf("first page must remain usable when ranked-window persistence fails: %v", err)
	}
	if len(response.Items) != 1 || response.NextContinuation != nil {
		t.Fatalf("persistence failure leaked continuation: %+v", response)
	}
	if response.TerminalOutcome != FeedTerminalDegraded ||
		response.FailureStage != FailureStageRankedWindowUnavailable {
		t.Fatalf("persistence failure terminal = (%s,%s)", response.TerminalOutcome, response.FailureStage)
	}
}

func newRankedWindowContinuationFixture(
	t *testing.T,
) (*Engine, GetFeedRequest, *RankedFeedContinuation) {
	t.Helper()
	const digest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	candidates := []ContentCandidate{
		{ContentID: "post-binding-1", ContentType: "image", AuthorID: "author-binding-1", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_binding", ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "post-binding-2", ContentType: "video", AuthorID: "author-binding-2", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_binding", ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "post-binding-3", ContentType: "article", AuthorID: "author-binding-3", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: "rel_binding", ManifestDigest: digest, LifecycleStatus: "active"},
	}
	engine := NewEngine(
		NewHotPath(newMockRedis()),
		[]CandidateSource{terminalRecallSource{candidates: candidates}},
		WithPolicyStore(noExplorePolicyStore()),
	)
	request := GetFeedRequest{
		UserID: "actor-binding", PersonaID: "persona-binding", SessionID: "session-binding",
		RankedWindowSubjectID: "actor\x00actor-binding",
		FeedType:              FeedDiscovery, Sort: FeedSortRecommend, Surface: "home", ChannelID: "recommend",
		FeedRequestID: "frq_binding", ActiveReleaseID: "rel_binding",
		ActiveManifestDigest: digest, Limit: 1, DeferDeliveryAccounting: true,
	}
	first, err := engine.GetFeed(context.Background(), request)
	if err != nil || first.NextContinuation == nil {
		t.Fatalf("create binding fixture: response=%+v err=%v", first, err)
	}
	return engine, request, first.NextContinuation
}

type rankedWindowTTLRedis struct {
	*mockRedisClient
	muTTL       sync.Mutex
	atomicTTLs  []time.Duration
	expireCalls int
}

func (r *rankedWindowTTLRedis) CreateBoundedImmutableRecordAtomic(
	ctx context.Context,
	request boundedrecord.Request,
) (boundedrecord.Result, error) {
	r.muTTL.Lock()
	r.atomicTTLs = append(r.atomicTTLs, request.TTL)
	r.muTTL.Unlock()
	return r.mockRedisClient.CreateBoundedImmutableRecordAtomic(
		ctx,
		request,
	)
}

func (r *rankedWindowTTLRedis) Expire(
	ctx context.Context,
	key string,
	ttl time.Duration,
) error {
	r.muTTL.Lock()
	r.expireCalls++
	r.muTTL.Unlock()
	return r.mockRedisClient.Expire(ctx, key, ttl)
}

func TestRedisRankedFeedWindowAtomicWinnerAndNonSlidingTTL(t *testing.T) {
	baseTime := time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
	now := baseTime
	redis := &rankedWindowTTLRedis{mockRedisClient: newMockRedis()}
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now:         func() time.Time { return now },
		newWindowID: func() (string, error) {
			return "rfw_set_nx_winner", nil
		},
	}
	window := testRankedFeedWindow(t)

	results := make(chan rankedFeedWindow, 2)
	errorsCh := make(chan error, 2)
	var group sync.WaitGroup
	for range 2 {
		group.Add(1)
		go func() {
			defer group.Done()
			created, err := store.Create(context.Background(), window)
			results <- created
			errorsCh <- err
		}()
	}
	group.Wait()
	close(results)
	close(errorsCh)
	for err := range errorsCh {
		if err != nil {
			t.Fatalf("concurrent Create: %v", err)
		}
	}
	for result := range results {
		if result.WindowID != "rfw_set_nx_winner" || !result.CreatedAt.Equal(baseTime) {
			t.Fatalf("SET NX loser did not return persisted winner: %+v", result)
		}
	}
	redis.muTTL.Lock()
	if len(redis.atomicTTLs) != 2 || redis.atomicTTLs[0] != RankedFeedWindowTTL ||
		redis.atomicTTLs[1] != RankedFeedWindowTTL {
		t.Fatalf("atomic create TTLs = %+v", redis.atomicTTLs)
	}
	redis.muTTL.Unlock()

	now = baseTime.Add(5 * time.Minute)
	loaded, err := store.Load(context.Background(), "actor\x00actor-window", "rfw_set_nx_winner")
	if err != nil || !loaded.ExpiresAt.Equal(baseTime.Add(RankedFeedWindowTTL)) {
		t.Fatalf("load before expiry: window=%+v err=%v", loaded, err)
	}
	redis.muTTL.Lock()
	if redis.expireCalls != 0 {
		t.Fatalf("Load refreshed Redis TTL %d times", redis.expireCalls)
	}
	redis.muTTL.Unlock()

	now = baseTime.Add(RankedFeedWindowTTL + time.Nanosecond)
	if _, err := store.Load(context.Background(), "actor\x00actor-window", "rfw_set_nx_winner"); !errors.Is(err, ErrRankedFeedWindowNotFound) {
		t.Fatalf("expired window error = %v, want ErrRankedFeedWindowNotFound", err)
	}
}

func TestRedisRankedFeedWindowAtomicWinnerRejectsProvenanceMismatch(t *testing.T) {
	store := &redisRankedFeedWindowStore{
		redis:       newMockRedis(),
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now:         func() time.Time { return time.Date(2026, 7, 28, 11, 0, 0, 0, time.UTC) },
		newWindowID: func() (string, error) {
			return "rfw_version_conflict", nil
		},
	}
	winner := testRankedFeedWindow(t)
	if _, err := store.Create(context.Background(), winner); err != nil {
		t.Fatalf("create winner: %v", err)
	}

	mutations := []struct {
		name   string
		mutate func(*rankedFeedWindow)
	}{
		{name: "candidate", mutate: func(v *rankedFeedWindow) { v.Provenance.CandidateWatermark = "sha256:other" }},
		{name: "policy", mutate: func(v *rankedFeedWindow) {
			policyDigest := "sha256:" + strings.Repeat("e", 64)
			v.Provenance.PolicyDigest = policyDigest
			v.Attribution.PolicyDigest = policyDigest
		}},
		{name: "scorer", mutate: func(v *rankedFeedWindow) { v.Provenance.ScorerPath = "rule_fallback" }},
		{name: "feature", mutate: func(v *rankedFeedWindow) { v.Provenance.FeatureSnapshotAt = "2026-07-28T10:00:00Z" }},
	}
	for _, mutation := range mutations {
		t.Run(mutation.name, func(t *testing.T) {
			contender := winner
			mutation.mutate(&contender)
			_, err := store.Create(context.Background(), contender)
			if !errors.Is(err, ErrRankedFeedWindowBindingMismatch) {
				t.Fatalf("provenance conflict error = %v, want ErrRankedFeedWindowBindingMismatch", err)
			}
		})
	}
}

func TestRankedFeedWindowPayloadHasNoSchemaVersionAndRejectsVersionEnvelope(t *testing.T) {
	redis := newMockRedis()
	now := time.Date(2026, 7, 29, 12, 0, 0, 0, time.UTC)
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now:         func() time.Time { return now },
		newWindowID: func() (string, error) {
			return "rfw_single_track_schema", nil
		},
	}
	created, err := store.Create(context.Background(), testRankedFeedWindow(t))
	if err != nil {
		t.Fatalf("create canonical ranked window: %v", err)
	}
	key := rankedFeedWindowKey("actor\x00actor-window", created.WindowID)
	raw := redis.data[key]
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw), &payload); err != nil {
		t.Fatalf("decode canonical payload: %v", err)
	}
	if _, exists := payload["version"]; exists {
		t.Fatalf("canonical ranked window retained a schema-version envelope: %s", raw)
	}
	payload["version"] = 1
	versioned, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("encode forbidden version envelope: %v", err)
	}
	if _, err := decodeRankedFeedWindow(
		string(versioned),
		created.Binding.SubjectHash,
		created.WindowID,
		now,
	); !errors.Is(err, ErrRankedFeedWindowStoreUnavailable) {
		t.Fatalf("version envelope error=%v, want fail-closed decode error", err)
	}
}

func TestRedisRankedFeedWindowRejectsMissingSessionBinding(t *testing.T) {
	store := NewRedisRankedFeedWindowStore(
		newMockRedis(),
		DefaultRankedFeedWindowQuotaPolicy(),
	)
	window := testRankedFeedWindow(t)
	window.Binding.SessionID = ""
	if _, err := store.Create(context.Background(), window); !errors.Is(err, ErrRankedFeedWindowInvalid) {
		t.Fatalf("missing session binding error = %v, want ErrRankedFeedWindowInvalid", err)
	}
}

func TestRankedFeedWindowPayloadHardBoundaryAndOversizedFailClosed(t *testing.T) {
	if err := validateRankedFeedWindowPayloadSize(RankedFeedWindowMaxPayloadBytes); err != nil {
		t.Fatalf("exact payload hard limit rejected: %v", err)
	}
	if err := validateRankedFeedWindowPayloadSize(RankedFeedWindowMaxPayloadBytes + 1); !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
		t.Fatalf("payload above hard limit error=%v, want ErrRankedFeedWindowPayloadTooLarge", err)
	}

	redis := newMockRedis()
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now: func() time.Time {
			return time.Date(2026, 7, 29, 12, 0, 0, 0, time.UTC)
		},
		newWindowID: func() (string, error) { return "rfw_payload_rejected", nil },
	}
	oversized := measurementRankedFeedWindow(t, RankedFeedWindowMaxItems, 15, 15)
	if _, err := store.Create(context.Background(), oversized); !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
		t.Fatalf("oversized Create error=%v, want ErrRankedFeedWindowPayloadTooLarge", err)
	}
	redis.mu.RLock()
	persistedCount := len(redis.data)
	redis.mu.RUnlock()
	if persistedCount != 0 {
		t.Fatalf("oversized payload reached Redis: persisted keys=%d", persistedCount)
	}

	actorID := "actor-oversized-load"
	windowID := "rfw_oversized_load"
	redis.mu.Lock()
	redis.data[rankedFeedWindowKey(actorID, windowID)] = strings.Repeat("x", RankedFeedWindowMaxPayloadBytes+1)
	redis.mu.Unlock()
	if _, err := store.Load(context.Background(), actorID, windowID); !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
		t.Fatalf("oversized Load error=%v, want ErrRankedFeedWindowPayloadTooLarge", err)
	}
}

func TestRankedFeedWindowChunkedMarshalUsesExactWholePayloadBudget(t *testing.T) {
	window := measurementRankedFeedWindow(t, 3, 2, 1)
	wholePayload, err := json.Marshal(window)
	if err != nil {
		t.Fatalf("marshal reference window: %v", err)
	}

	encoded, measuredBytes, err := marshalRankedFeedWindowWithinBudget(
		window,
		len(wholePayload),
	)
	if err != nil {
		t.Fatalf("chunked marshal at exact budget: %v", err)
	}
	if measuredBytes != len(wholePayload) || len(encoded) != len(wholePayload) {
		t.Fatalf(
			"chunked payload bytes=(measured:%d encoded:%d), want %d",
			measuredBytes,
			len(encoded),
			len(wholePayload),
		)
	}
	if !bytes.Equal(encoded, wholePayload) {
		t.Fatal("chunked payload wire representation drifted from canonical JSON")
	}
	var decoded rankedFeedWindow
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		t.Fatalf("decode chunked payload: %v", err)
	}
	if decoded.WindowID != window.WindowID || len(decoded.Items) != len(window.Items) {
		t.Fatalf("chunked payload semantic drift: %+v", decoded)
	}

	_, rejectedBytes, err := marshalRankedFeedWindowWithinBudget(
		window,
		len(wholePayload)-1,
	)
	if !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) ||
		rejectedBytes <= len(wholePayload)-1 {
		t.Fatalf(
			"exact budget overflow=(bytes:%d err:%v), want payload-too-large",
			rejectedBytes,
			err,
		)
	}
}

func TestRankedFeedWindowChunkedMarshalStopsAtFirstBudgetOverflow(t *testing.T) {
	window := testRankedFeedWindow(t)
	first := window.Items[0]
	first.Item.Title = strings.Repeat("x", 2048)
	poison := window.Items[0]
	poison.Ordinal = 2
	poison.Item.ContentID = "post-window-poison"
	poison.Training.ItemFeatures = map[string]any{
		"must_not_be_marshaled_after_overflow": func() {},
	}
	window.Items = []rankedFeedWindowItem{first, poison}

	emptyWindow := window
	emptyWindow.Items = []rankedFeedWindowItem{}
	emptyPayload, err := json.Marshal(emptyWindow)
	if err != nil {
		t.Fatalf("marshal empty reference envelope: %v", err)
	}
	budget := len(emptyPayload) + 64
	_, measuredBytes, err := marshalRankedFeedWindowWithinBudget(window, budget)
	if !errors.Is(err, ErrRankedFeedWindowPayloadTooLarge) {
		t.Fatalf(
			"chunked overflow error=%v, want payload-too-large before poison item",
			err,
		)
	}
	if measuredBytes <= budget {
		t.Fatalf("chunked overflow measured bytes=%d, budget=%d", measuredBytes, budget)
	}
}

func TestRankedFeedWindowNinthEvictsFirstAndKeepsSubjectsIsolated(t *testing.T) {
	redis := newMockRedis()
	nextID := 0
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now: func() time.Time {
			return time.Date(2026, 7, 29, 13, 0, 0, 0, time.UTC)
		},
		newWindowID: func() (string, error) {
			nextID++
			return fmt.Sprintf("rfw_quota_%02d", nextID), nil
		},
	}

	otherSubject := "actor\x00actor-quota-other"
	otherSubjectWindow := testRankedFeedWindow(t)
	otherSubjectWindow.Binding.ActorID = "actor-quota-other"
	otherSubjectWindow.Binding.SubjectHash = rankedFeedWindowSubjectHash(otherSubject)
	otherCreated, err := store.Create(context.Background(), otherSubjectWindow)
	if err != nil {
		t.Fatalf("create other subject window: %v", err)
	}

	primarySubject := "actor\x00actor-quota-primary"
	primarySubjectWindow := testRankedFeedWindow(t)
	primarySubjectWindow.Binding.ActorID = "actor-quota-primary"
	primarySubjectWindow.Binding.SubjectHash = rankedFeedWindowSubjectHash(primarySubject)
	createdIDs := make([]string, 0, RankedFeedWindowMaxActivePerSubject+1)
	for index := 0; index < RankedFeedWindowMaxActivePerSubject+1; index++ {
		created, createErr := store.Create(context.Background(), primarySubjectWindow)
		if createErr != nil {
			t.Fatalf("create primary subject window %d: %v", index+1, createErr)
		}
		createdIDs = append(createdIDs, created.WindowID)
	}

	if _, err := store.Load(context.Background(), primarySubject, createdIDs[0]); !errors.Is(err, ErrRankedFeedWindowNotFound) {
		t.Fatalf("first of nine windows error=%v, want eviction/not found", err)
	}
	for _, windowID := range createdIDs[1:] {
		if _, err := store.Load(context.Background(), primarySubject, windowID); err != nil {
			t.Fatalf("active primary subject window %s missing: %v", windowID, err)
		}
	}
	if _, err := store.Load(
		context.Background(),
		otherSubject,
		otherCreated.WindowID,
	); err != nil {
		t.Fatalf("primary subject quota evicted other subject window: %v", err)
	}

	redis.mu.RLock()
	primaryIndexSize := rankedWindowOwnerCountLocked(
		redis,
		rankedFeedWindowSubjectHash(primarySubject),
	)
	otherIndexSize := rankedWindowOwnerCountLocked(
		redis,
		rankedFeedWindowSubjectHash(otherSubject),
	)
	redis.mu.RUnlock()
	if primaryIndexSize != RankedFeedWindowMaxActivePerSubject || otherIndexSize != 1 {
		t.Fatalf("subject quota indexes=(primary:%d other:%d), want (%d,1)", primaryIndexSize, otherIndexSize, RankedFeedWindowMaxActivePerSubject)
	}
}

func TestRankedFeedWindowAnonymousSessionsDoNotShareGlobalFallbackQuota(t *testing.T) {
	redis := newMockRedis()
	nextID := 0
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now: func() time.Time {
			return time.Date(2026, 7, 29, 13, 30, 0, 0, time.UTC)
		},
		newWindowID: func() (string, error) {
			nextID++
			return fmt.Sprintf("rfw_anonymous_quota_%02d", nextID), nil
		},
	}

	const anonymousFallbackActor = "anonymous-fallback-actor"
	firstSubject := "anonymous-session\x00session-a"
	secondSubject := "anonymous-session\x00session-b"
	firstWindow := testRankedFeedWindow(t)
	firstWindow.Binding.ActorID = anonymousFallbackActor
	firstWindow.Binding.SessionID = "session-a"
	firstWindow.Binding.SubjectHash = rankedFeedWindowSubjectHash(firstSubject)

	firstIDs := make([]string, 0, RankedFeedWindowMaxActivePerSubject)
	for index := 0; index < RankedFeedWindowMaxActivePerSubject; index++ {
		created, err := store.Create(context.Background(), firstWindow)
		if err != nil {
			t.Fatalf("create anonymous session A window %d: %v", index+1, err)
		}
		firstIDs = append(firstIDs, created.WindowID)
	}

	secondWindow := testRankedFeedWindow(t)
	secondWindow.Binding.ActorID = anonymousFallbackActor
	secondWindow.Binding.SessionID = "session-b"
	secondWindow.Binding.SubjectHash = rankedFeedWindowSubjectHash(secondSubject)
	if _, err := store.Create(context.Background(), secondWindow); err != nil {
		t.Fatalf("create anonymous session B window: %v", err)
	}

	if _, err := store.Load(context.Background(), firstSubject, firstIDs[0]); err != nil {
		t.Fatalf("session B evicted session A's valid first window: %v", err)
	}
	redis.mu.RLock()
	firstIndexSize := rankedWindowOwnerCountLocked(
		redis,
		rankedFeedWindowSubjectHash(firstSubject),
	)
	secondIndexSize := rankedWindowOwnerCountLocked(
		redis,
		rankedFeedWindowSubjectHash(secondSubject),
	)
	redis.mu.RUnlock()
	if firstIndexSize != RankedFeedWindowMaxActivePerSubject || secondIndexSize != 1 {
		t.Fatalf(
			"anonymous session indexes=(first:%d second:%d), want (%d,1)",
			firstIndexSize,
			secondIndexSize,
			RankedFeedWindowMaxActivePerSubject,
		)
	}
}

func TestRankedFeedWindowGlobalShardCapRejectsWithoutCrossSubjectEviction(
	t *testing.T,
) {
	redis := newMockRedis()
	nextID := 0
	policy := boundedrecord.Policy{
		ShardCount:                 1,
		MaximumLiveRecordsPerShard: 2,
		MaximumLiveBytesPerShard:   1 << 20,
		MaximumLiveRecordsPerOwner: 2,
	}
	store := &redisRankedFeedWindowStore{
		redis:       redis,
		quotaPolicy: policy,
		now: func() time.Time {
			return time.Date(2026, 7, 29, 13, 45, 0, 0, time.UTC)
		},
		newWindowID: func() (string, error) {
			nextID++
			return fmt.Sprintf("rfw_global_quota_%02d", nextID), nil
		},
	}
	subjects := []string{
		"actor\x00global-quota-a",
		"actor\x00global-quota-b",
		"actor\x00global-quota-c",
	}
	createdIDs := make([]string, 0, 2)
	for index, subject := range subjects {
		window := testRankedFeedWindow(t)
		window.Binding.ActorID = fmt.Sprintf("global-quota-%c", 'a'+index)
		window.Binding.SubjectHash = rankedFeedWindowSubjectHash(subject)
		created, err := store.Create(context.Background(), window)
		if index < 2 {
			if err != nil {
				t.Fatalf("seed global quota subject %d: %v", index, err)
			}
			createdIDs = append(createdIDs, created.WindowID)
			continue
		}
		if !errors.Is(err, ErrRankedFeedWindowStoreUnavailable) ||
			!errors.Is(err, boundedrecord.ErrShardKeyQuota) {
			t.Fatalf(
				"global quota error=%v, want store unavailable + shard key quota",
				err,
			)
		}
	}
	for index := range createdIDs {
		if _, err := store.Load(
			context.Background(),
			subjects[index],
			createdIDs[index],
		); err != nil {
			t.Fatalf("cross-subject record %d was evicted: %v", index, err)
		}
	}
}

func TestRankedFeedWindowAtomicCapabilityMissingFailsClosedWithoutSetNXFallback(t *testing.T) {
	redis := newMockRedis()
	store := &redisRankedFeedWindowStore{
		redis:       redisWithoutAtomicCapability{RedisPipelineClient: redis},
		quotaPolicy: DefaultRankedFeedWindowQuotaPolicy(),
		now: func() time.Time {
			return time.Date(2026, 7, 29, 14, 0, 0, 0, time.UTC)
		},
		newWindowID: func() (string, error) { return "rfw_atomic_unavailable", nil },
	}
	_, err := store.Create(context.Background(), testRankedFeedWindow(t))
	if !errors.Is(err, ErrRankedFeedWindowStoreUnavailable) ||
		!errors.Is(err, ErrRankedFeedWindowAtomicUnavailable) {
		t.Fatalf("missing atomic capability error=%v, want fail-closed store+atomic errors", err)
	}
	redis.mu.RLock()
	persistedCount := len(redis.data)
	redis.mu.RUnlock()
	if persistedCount != 0 {
		t.Fatalf("missing atomic capability fell back to SetNX: persisted keys=%d", persistedCount)
	}
}

func TestRankedFeedWindowValueIndexAndMetadataUseSameFixedQuotaShard(t *testing.T) {
	subjectHash := rankedFeedWindowSubjectHash("subject-hash-slot")
	windowKey, indexKey, metadataKey, err := rankedFeedWindowQuotaKeys(
		subjectHash,
		"rfw_hash_slot",
		DefaultRankedFeedWindowQuotaPolicy(),
	)
	if err != nil {
		t.Fatalf("derive ranked window quota keys: %v", err)
	}
	windowTagStart := strings.Index(windowKey, "{")
	windowTagEnd := strings.Index(windowKey, "}")
	indexTagStart := strings.Index(indexKey, "{")
	indexTagEnd := strings.Index(indexKey, "}")
	metadataTagStart := strings.Index(metadataKey, "{")
	metadataTagEnd := strings.Index(metadataKey, "}")
	if windowTagStart < 0 || windowTagEnd <= windowTagStart ||
		indexTagStart < 0 || indexTagEnd <= indexTagStart ||
		metadataTagStart < 0 || metadataTagEnd <= metadataTagStart {
		t.Fatalf(
			"ranked window keys lack Redis hash tags: window=%q index=%q metadata=%q",
			windowKey,
			indexKey,
			metadataKey,
		)
	}
	windowTag := windowKey[windowTagStart : windowTagEnd+1]
	if windowTag != indexKey[indexTagStart:indexTagEnd+1] ||
		windowTag != metadataKey[metadataTagStart:metadataTagEnd+1] {
		t.Fatalf(
			"ranked window keys cross slots: window=%q index=%q metadata=%q",
			windowKey,
			indexKey,
			metadataKey,
		)
	}
	if !strings.HasPrefix(windowKey, "rec:ranked_feed_window:") ||
		!strings.HasPrefix(indexKey, "rec:ranked_feed_window_index:") ||
		!strings.HasPrefix(metadataKey, "rec:ranked_feed_window_metadata:") {
		t.Fatalf(
			"ranked window keys are not canonical: %q %q %q",
			windowKey,
			indexKey,
			metadataKey,
		)
	}
}

type redisWithoutAtomicCapability struct {
	RedisPipelineClient
}

func rankedWindowOwnerCountLocked(
	redis *mockRedisClient,
	ownerDigest string,
) int {
	count := 0
	for _, owners := range redis.rankedFeedWindowOwners {
		for _, owner := range owners {
			if owner == ownerDigest {
				count++
			}
		}
	}
	return count
}

func testRankedFeedWindow(t *testing.T) rankedFeedWindow {
	t.Helper()
	item := FeedItem{
		ContentID: "post-window", ContentType: "image", AuthorID: "author-window",
		trainingFeatures: newTrainingFeatureSnapshot(
			&UserFeatureVector{},
			CandidateInput{ContentID: "post-window", ContentType: "image", AuthorID: "author-window"},
			time.Date(2026, 7, 28, 9, 59, 0, 0, time.UTC),
		),
		rank: 1,
	}
	windowItem, err := newRankedFeedWindowItem(item, 1)
	if err != nil {
		t.Fatalf("new ranked window item: %v", err)
	}
	return rankedFeedWindow{
		Binding: rankedFeedWindowBinding{
			SubjectHash: rankedFeedWindowSubjectHash("actor\x00actor-window"),
			ActorID:     "actor-window", PersonaID: "persona-window", SessionID: "session-window",
			FeedType: FeedDiscovery, Sort: FeedSortRecommend, Surface: "home", ChannelID: "recommend",
			FeedRequestID: "frq_window", ReleaseID: "rel_window",
			ManifestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		Provenance: rankedFeedWindowProvenance{
			CandidateWatermark: "sha256:" + strings.Repeat("c", 64), PolicyDigest: "sha256:" + strings.Repeat("d", 64),
			FeatureSnapshotAt: "2026-07-28T09:59:00Z", ScorerPath: "rule",
		},
		Items: []rankedFeedWindowItem{windowItem},
		Attribution: DeliveryAttribution{
			FeedRequestID: "frq_window", PersonaID: "persona-window", ChannelID: "recommend",
			ModelBucket: "rule", ScoringBucket: "control", PolicyDigest: "sha256:" + strings.Repeat("d", 64),
		},
		TerminalOutcome: FeedTerminalSuccess,
		FailureStage:    FailureStageNone,
	}
}
