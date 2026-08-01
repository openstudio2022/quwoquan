// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package api_integration

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestDiscoveryFeedCanonicalReadExplainUsesDeclaredIndex(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	collection := db.Collection("rm_discovery_feed")
	projector := recinfra.NewDiscoveryFeedProjector(db)
	if err := projector.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure discovery feed indexes: %v", err)
	}

	const releaseID = "rel_feed_explain_contract"
	const manifestDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"releaseId": releaseID})
	})
	seed := make([]any, 0, 160)
	now := time.Now().UTC()
	for index := 0; index < 160; index++ {
		seed = append(seed, bson.M{
			"postId":          releaseID + "_" + leftPadFeedIndex(index),
			"status":          "published",
			"visibility":      "public",
			"sourceOwner":     "qwq_data",
			"releaseId":       releaseID,
			"manifestDigest":  manifestDigest,
			"lifecycleStatus": "active",
			"recScore":        float64(160 - index),
			"publishedAt":     now.Add(-time.Duration(index) * time.Minute),
			"body":            strings.Repeat("must-not-be-read", 128),
			"mediaItems":      []any{bson.M{"url": "https://example.invalid/full"}},
		})
	}
	if _, err := collection.InsertMany(ctx, seed); err != nil {
		t.Fatalf("seed discovery feed explain corpus: %v", err)
	}

	filter := bson.D{
		{Key: "status", Value: "published"},
		{Key: "visibility", Value: "public"},
		{Key: "sourceOwner", Value: "qwq_data"},
		{Key: "releaseId", Value: releaseID},
		{Key: "manifestDigest", Value: manifestDigest},
		{Key: "lifecycleStatus", Value: "active"},
	}
	sortOrder := bson.D{
		{Key: "recScore", Value: -1},
		{Key: "publishedAt", Value: -1},
		{Key: "postId", Value: -1},
	}
	assertDiscoveryFeedExplainUsesIndex(
		t,
		db,
		filter,
		sortOrder,
		"idx_df_active_release_recency",
	)
	assertDiscoveryFeedExplainUsesIndex(
		t,
		db,
		bson.D{
			{Key: "status", Value: "published"},
			{Key: "visibility", Value: "public"},
			{Key: "$or", Value: bson.A{
				bson.M{"$and": bson.A{
					bson.M{"sourceOwner": bson.M{"$ne": "qwq_data"}},
					bson.M{"supplySource": bson.M{"$ne": "data_engineering"}},
				}},
				bson.M{
					"sourceOwner": "qwq_data", "releaseId": releaseID,
					"manifestDigest": manifestDigest, "lifecycleStatus": "active",
				},
			}},
		},
		sortOrder,
		"idx_df_recommend_recency",
	)

	var row bson.M
	err := collection.FindOne(
		ctx,
		filter,
		options.FindOne().
			SetProjection(recinfra.DiscoveryFeedCandidateProjection()).
			SetSort(sortOrder),
	).Decode(&row)
	if err != nil {
		t.Fatalf("read minimal discovery candidate: %v", err)
	}
	if _, ok := row["body"]; ok {
		t.Fatalf("minimal discovery candidate leaked body: %#v", row)
	}
	if _, ok := row["mediaItems"]; ok {
		t.Fatalf("minimal discovery candidate leaked mediaItems: %#v", row)
	}
}

func assertDiscoveryFeedExplainUsesIndex(
	t *testing.T,
	db *mongo.Database,
	filter bson.D,
	sortOrder bson.D,
	indexName string,
) {
	t.Helper()
	var explain bson.M
	err := db.RunCommand(context.Background(), bson.D{
		{Key: "explain", Value: bson.D{
			{Key: "find", Value: "rm_discovery_feed"},
			{Key: "filter", Value: filter},
			{Key: "sort", Value: sortOrder},
			{Key: "projection", Value: recinfra.DiscoveryFeedCandidateProjection()},
			{Key: "hint", Value: indexName},
			{Key: "limit", Value: 20},
		}},
		{Key: "verbosity", Value: "queryPlanner"},
	}).Decode(&explain)
	if err != nil {
		t.Fatalf("explain discovery read with %s: %v", indexName, err)
	}
	rawPlan, err := json.Marshal(explain)
	if err != nil {
		t.Fatalf("marshal discovery explain: %v", err)
	}
	plan := strings.ToUpper(string(rawPlan))
	if !strings.Contains(plan, "IXSCAN") ||
		strings.Contains(plan, "COLLSCAN") ||
		strings.Contains(plan, `"STAGE":"SORT"`) {
		t.Fatalf("discovery read must use index order without scan/sort: %s", plan)
	}
	if !strings.Contains(plan, strings.ToUpper(indexName)) {
		t.Fatalf("discovery read used unexpected index, want=%s plan=%s", indexName, plan)
	}
}

func TestActiveSupplyReadbackSingleflightAndReleaseInvalidation(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-feed-cache"
	const releaseA = "rel_feed_cache_a"
	const releaseB = "rel_feed_cache_b"
	const digestA = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	const digestB = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
	state := db.Collection("data_release_state")
	posts := db.Collection("posts")
	feed := db.Collection("rm_discovery_feed")
	t.Cleanup(func() {
		_, _ = state.DeleteMany(context.Background(), bson.M{"environment": environment})
		_, _ = posts.DeleteMany(context.Background(), bson.M{"releaseId": bson.M{"$in": bson.A{releaseA, releaseB}}})
		_, _ = feed.DeleteMany(context.Background(), bson.M{"releaseId": bson.M{"$in": bson.A{releaseA, releaseB}}})
	})
	_, err := state.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{
			"environment": environment, "sourceOwner": "qwq_data", "status": "active",
			"activeReleaseId": releaseA, "manifestDigest": digestA,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		t.Fatalf("seed release state: %v", err)
	}
	seedActiveSupplyProjection(t, posts, feed, releaseA, digestA)
	seedActiveSupplyProjection(t, posts, feed, releaseB, digestB)
	playableVideos := &countingPlayableVideoReader{delay: 40 * time.Millisecond}
	reader := persistence.NewMongoActiveSupplyReader(
		db,
		environment,
		persistence.WithActiveSupplyCachePolicy(time.Minute, 0),
		persistence.WithPlayableVideoSupplyReader(playableVideos),
	)

	const callers = 12
	start := make(chan struct{})
	errs := make(chan error, callers)
	var wait sync.WaitGroup
	for index := 0; index < callers; index++ {
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			snapshot, readErr := reader.ActiveSupplySnapshot(ctx)
			if readErr == nil && (!snapshot.Ready() || snapshot.ActiveReleaseID != releaseA) {
				readErr = errors.New("unexpected active supply snapshot")
			}
			errs <- readErr
		}()
	}
	close(start)
	wait.Wait()
	close(errs)
	for readErr := range errs {
		if readErr != nil {
			t.Fatalf("concurrent active supply read: %v", readErr)
		}
	}
	if calls := playableVideos.Calls(); calls != 1 {
		t.Fatalf("same release readiness work calls=%d want=1", calls)
	}

	_, err = state.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{"activeReleaseId": releaseB, "manifestDigest": digestB}},
	)
	if err != nil {
		t.Fatalf("switch active release: %v", err)
	}
	snapshot, err := reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("read switched active release: %v", err)
	}
	if snapshot.ActiveReleaseID != releaseB || snapshot.ManifestDigest != digestB {
		t.Fatalf("old release snapshot reused after switch: %+v", snapshot)
	}
	if calls := playableVideos.Calls(); calls != 2 {
		t.Fatalf("release switch must invalidate readback cache, calls=%d want=2", calls)
	}
}

func TestActiveSupplyReadbackRejectsReleaseSwitchDuringInflightCounts(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	const environment = "api-integration-feed-cache-race"
	const releaseA = "rel_feed_cache_race_a"
	const releaseB = "rel_feed_cache_race_b"
	const digestA = "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
	const digestB = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
	state := db.Collection("data_release_state")
	posts := db.Collection("posts")
	feed := db.Collection("rm_discovery_feed")
	t.Cleanup(func() {
		_, _ = state.DeleteMany(context.Background(), bson.M{"environment": environment})
		_, _ = posts.DeleteMany(context.Background(), bson.M{"releaseId": bson.M{"$in": bson.A{releaseA, releaseB}}})
		_, _ = feed.DeleteMany(context.Background(), bson.M{"releaseId": bson.M{"$in": bson.A{releaseA, releaseB}}})
	})
	_, err := state.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{
			"environment": environment, "sourceOwner": "qwq_data", "status": "active",
			"activeReleaseId": releaseA, "manifestDigest": digestA,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		t.Fatalf("seed release state: %v", err)
	}
	seedActiveSupplyProjection(t, posts, feed, releaseA, digestA)
	seedActiveSupplyProjection(t, posts, feed, releaseB, digestB)
	playableVideos := newReleaseSwitchPlayableVideoReader()
	reader := persistence.NewMongoActiveSupplyReader(
		db,
		environment,
		persistence.WithActiveSupplyCachePolicy(time.Minute, 0),
		persistence.WithPlayableVideoSupplyReader(playableVideos),
	)

	result := make(chan error, 1)
	go func() {
		_, readErr := reader.ActiveSupplySnapshot(ctx)
		result <- readErr
	}()
	select {
	case <-playableVideos.started:
	case <-time.After(5 * time.Second):
		t.Fatal("active supply count did not reach controlled dependency")
	}
	_, err = state.UpdateOne(ctx,
		bson.M{"environment": environment, "sourceOwner": "qwq_data"},
		bson.M{"$set": bson.M{"activeReleaseId": releaseB, "manifestDigest": digestB}},
	)
	if err != nil {
		t.Fatalf("switch active release during readback: %v", err)
	}
	close(playableVideos.release)
	if readErr := <-result; readErr == nil || !strings.Contains(readErr.Error(), "changed during supply readback") {
		t.Fatalf("inflight old release read must fail closed, err=%v", readErr)
	}

	snapshot, err := reader.ActiveSupplySnapshot(ctx)
	if err != nil {
		t.Fatalf("read switched release after rejected old flight: %v", err)
	}
	if snapshot.ActiveReleaseID != releaseB || snapshot.ManifestDigest != digestB {
		t.Fatalf("switched release snapshot = %+v", snapshot)
	}
	if calls := playableVideos.Calls(); calls != 2 {
		t.Fatalf("old flight must not populate cache, premium calls=%d want=2", calls)
	}
}

type countingPlayableVideoReader struct {
	mu    sync.Mutex
	calls int
	delay time.Duration
}

type releaseSwitchPlayableVideoReader struct {
	mu      sync.Mutex
	calls   int
	started chan struct{}
	release chan struct{}
}

func newReleaseSwitchPlayableVideoReader() *releaseSwitchPlayableVideoReader {
	return &releaseSwitchPlayableVideoReader{
		started: make(chan struct{}),
		release: make(chan struct{}),
	}
}

func (reader *releaseSwitchPlayableVideoReader) CountActiveReleasePlayableVideos(
	ctx context.Context,
	_ string,
	_ string,
) (int64, error) {
	reader.mu.Lock()
	reader.calls++
	call := reader.calls
	reader.mu.Unlock()
	if call == 1 {
		close(reader.started)
		select {
		case <-ctx.Done():
			return 0, ctx.Err()
		case <-reader.release:
		}
	}
	return 1, nil
}

func (reader *releaseSwitchPlayableVideoReader) Calls() int {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	return reader.calls
}

func (reader *countingPlayableVideoReader) CountActiveReleasePlayableVideos(
	ctx context.Context,
	_ string,
	_ string,
) (int64, error) {
	reader.mu.Lock()
	reader.calls++
	reader.mu.Unlock()
	select {
	case <-ctx.Done():
		return 0, ctx.Err()
	case <-time.After(reader.delay):
		return 1, nil
	}
}

func (reader *countingPlayableVideoReader) Calls() int {
	reader.mu.Lock()
	defer reader.mu.Unlock()
	return reader.calls
}

func seedActiveSupplyProjection(
	t *testing.T,
	posts *mongo.Collection,
	feed *mongo.Collection,
	releaseID string,
	manifestDigest string,
) {
	t.Helper()
	ctx := context.Background()
	postID := releaseID + "_post"
	canonical := bson.M{
		"sourceOwner": "qwq_data", "releaseId": releaseID,
		"manifestDigest": manifestDigest, "lifecycleStatus": "active",
		"status": "published", "visibility": "public",
	}
	post := cloneFeedTestMap(canonical)
	post["_id"] = postID
	post["moderationStatus"] = "approved"
	if _, err := posts.InsertOne(ctx, post); err != nil {
		t.Fatalf("seed active supply post: %v", err)
	}
	row := cloneFeedTestMap(canonical)
	row["postId"] = postID
	if _, err := feed.InsertOne(ctx, row); err != nil {
		t.Fatalf("seed active supply feed row: %v", err)
	}
}

func cloneFeedTestMap(source bson.M) bson.M {
	out := make(bson.M, len(source))
	for key, value := range source {
		out[key] = value
	}
	return out
}

func leftPadFeedIndex(value int) string {
	const digits = "000"
	raw := string(rune('0' + value%10))
	if value >= 100 {
		return string(rune('0'+value/100)) + string(rune('0'+(value/10)%10)) + raw
	}
	if value >= 10 {
		return digits[:1] + string(rune('0'+value/10)) + raw
	}
	return digits[:2] + raw
}
