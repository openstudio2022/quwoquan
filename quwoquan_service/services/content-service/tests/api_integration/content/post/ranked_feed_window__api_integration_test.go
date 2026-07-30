// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
package api_integration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/boundedrecord"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

type rankedWindowStaticSource struct {
	candidates []rtrec.ContentCandidate
}

func (s rankedWindowStaticSource) Recall(
	_ context.Context,
	_ rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	return append([]rtrec.ContentCandidate(nil), s.candidates...), nil
}

func TestRankedFeedWindowRealRedisRejectsOverBudgetCanonicalProjection(t *testing.T) {
	const (
		releaseID = "rel_ranked_window_entry_budget_api"
		digest    = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
	)
	tags := make([]string, 30)
	for index := range tags {
		tags[index] = fmt.Sprintf("Topic/预算/%02d", index)
	}
	candidates := make([]rtrec.ContentCandidate, 0, 3)
	for index := 0; index < 3; index++ {
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID:   fmt.Sprintf("ranked-window-entry-budget-api-%02d", index),
			ContentType: "article", AuthorID: fmt.Sprintf("author-entry-budget-%02d", index),
			Title: strings.Repeat("题", 80), Tags: append([]string(nil), tags...),
			EntityRefs:  []string{"entity:homepage:over-canonical-combined-budget"},
			SourceOwner: "qwq_data", SupplySource: "data_engineering",
			ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active",
		})
	}
	engine := rtrec.NewEngine(
		rtrec.NewHotPath(rtredis.NewRecAdapter(requireTestRouter(t).Scene("rec"))),
		[]rtrec.CandidateSource{rankedWindowStaticSource{candidates: candidates}},
	)
	response, err := engine.GetFeed(context.Background(), rtrec.GetFeedRequest{
		UserID: "ranked-window-entry-budget-actor", PersonaID: "ranked-window-entry-budget-persona",
		SessionID: "ranked-window-entry-budget-session", RankedWindowSubjectID: "actor\x00ranked-window-entry-budget-actor",
		FeedType: rtrec.FeedDiscovery, Sort: rtrec.FeedSortRecommend, Surface: "home", ChannelID: "recommend",
		FeedRequestID: "frq_ranked_window_entry_budget_api", ActiveReleaseID: releaseID,
		ActiveManifestDigest: digest, Limit: 1, DeferDeliveryAccounting: true,
	})
	if err != nil {
		t.Fatalf("first page remains usable while window admission rejects invalid projection: %v", err)
	}
	if len(response.Items) != 1 {
		t.Fatalf("first page item count=%d, want 1", len(response.Items))
	}
	if response.NextContinuation != nil {
		t.Fatalf("over-budget canonical projection minted continuation: %+v", response.NextContinuation)
	}
}

func TestRankedFeedWindowRealRedisGlobalShardAdmissionDoesNotEvictOtherSubject(
	t *testing.T,
) {
	ctx := context.Background()
	policy := boundedrecord.Policy{
		ShardCount:                 4096,
		MaximumLiveRecordsPerShard: 2,
		MaximumLiveBytesPerShard:   4 * 1024 * 1024,
		MaximumLiveRecordsPerOwner: 2,
	}
	subjects, shard := collidingRankedWindowSubjects(t, policy, 3)
	tag := "{rfw-" + shard + "}"
	indexKey := "rec:ranked_feed_window_index:" + tag
	metadataKey := "rec:ranked_feed_window_metadata:" + tag
	recClient := requireTestRouter(t).Scene("rec")
	if err := recClient.Del(ctx, indexKey, metadataKey); err != nil {
		t.Fatalf("clear isolated ranked quota shard: %v", err)
	}
	t.Cleanup(func() {
		_ = recClient.Del(context.Background(), indexKey, metadataKey)
	})

	const (
		releaseID = "rel_ranked_global_quota_api"
		digest    = "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
	)
	candidates := []rtrec.ContentCandidate{
		{ContentID: "quota-api-1", ContentType: "image", AuthorID: "quota-author-1", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "quota-api-2", ContentType: "video", AuthorID: "quota-author-2", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "quota-api-3", ContentType: "article", AuthorID: "quota-author-3", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
	}
	engine := rtrec.NewEngine(
		rtrec.NewHotPath(
			rtredis.NewRecAdapter(recClient),
			rtrec.WithRankedFeedWindowQuotaPolicy(policy),
		),
		[]rtrec.CandidateSource{rankedWindowStaticSource{candidates: candidates}},
	)
	requests := make([]rtrec.GetFeedRequest, 0, len(subjects))
	continuations := make([]*rtrec.RankedFeedContinuation, 0, 2)
	for index, subject := range subjects {
		request := rtrec.GetFeedRequest{
			UserID:                  fmt.Sprintf("ranked-global-quota-%d", index),
			PersonaID:               fmt.Sprintf("ranked-global-quota-persona-%d", index),
			SessionID:               fmt.Sprintf("ranked-global-quota-session-%d", index),
			RankedWindowSubjectID:   subject,
			FeedType:                rtrec.FeedDiscovery,
			Sort:                    rtrec.FeedSortRecommend,
			Surface:                 "home",
			ChannelID:               "recommend",
			FeedRequestID:           fmt.Sprintf("frq_ranked_global_quota_%d", index),
			ActiveReleaseID:         releaseID,
			ActiveManifestDigest:    digest,
			Limit:                   1,
			DeferDeliveryAccounting: true,
		}
		response, err := engine.GetFeed(ctx, request)
		if err != nil {
			t.Fatalf("global quota first page %d: %v", index, err)
		}
		requests = append(requests, request)
		if index < 2 {
			if response.NextContinuation == nil {
				t.Fatalf("global quota admitted subject %d without continuation", index)
			}
			continuations = append(continuations, response.NextContinuation)
			subjectHash := rankedWindowSubjectDigest(subject)
			valueKey := fmt.Sprintf(
				"rec:ranked_feed_window:%s:%s:%s",
				tag,
				subjectHash,
				response.NextContinuation.WindowID,
			)
			t.Cleanup(func() {
				_ = recClient.Del(context.Background(), valueKey)
			})
			continue
		}
		if response.NextContinuation != nil ||
			response.TerminalOutcome != rtrec.FeedTerminalDegraded ||
			response.FailureStage != rtrec.FailureStageRankedWindowUnavailable {
			t.Fatalf("global quota rejection was not fail-closed: %+v", response)
		}
	}
	requests[0].Continuation = continuations[0]
	if _, err := engine.GetFeed(ctx, requests[0]); err != nil {
		t.Fatalf("rejected subject evicted admitted subject: %v", err)
	}
}

func collidingRankedWindowSubjects(
	t *testing.T,
	policy boundedrecord.Policy,
	count int,
) ([]string, string) {
	t.Helper()
	byShard := make(map[string][]string)
	for index := 0; index < 100000; index++ {
		subject := fmt.Sprintf("actor\x00ranked-quota-collision-%d", index)
		shard, err := policy.ShardForDigest(rankedWindowSubjectDigest(subject))
		if err != nil {
			t.Fatalf("map ranked quota subject: %v", err)
		}
		// Default production tests only use 256 shards (0000-00ff). Select an
		// isolated high shard so this bounded-policy case cannot disturb them.
		if shard <= "00ff" {
			continue
		}
		byShard[shard] = append(byShard[shard], subject)
		if len(byShard[shard]) == count {
			return byShard[shard], shard
		}
	}
	t.Fatalf("find %d ranked subjects in one isolated quota shard", count)
	return nil, ""
}

func rankedWindowSubjectDigest(subject string) string {
	digest := sha256.Sum256([]byte(subject))
	return hex.EncodeToString(digest[:16])
}

// TestRankedFeedWindowContinuationUsesRealRedisSnapshot proves the API
// integration composition crosses real MongoDB for the first recall and real
// Redis for continuation. Once a cursor has been issued, deleting the original
// Mongo candidates and adding a different live candidate set cannot alter the
// immutable continuation page.
func TestRankedFeedWindowContinuationUsesRealRedisSnapshot(t *testing.T) {
	ctx := context.Background()
	collection := requireMongoDB(t).Collection("rm_discovery_feed")
	const (
		releaseID = "rel_ranked_window_api"
		digest    = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	)
	oldIDs := make([]string, 0, 9)
	documents := make([]any, 0, 9)
	now := time.Now().UTC()
	contentTypes := []string{"image", "video", "article"}
	for index := 0; index < 9; index++ {
		contentID := fmt.Sprintf("ranked-window-api-old-%02d", index)
		oldIDs = append(oldIDs, contentID)
		documents = append(documents, bson.M{
			"postId": contentID, "contentType": contentTypes[index%len(contentTypes)],
			"authorId": fmt.Sprintf("ranked-window-api-author-%02d", index),
			"status":   "published", "visibility": "public", "publishedAt": now.Add(-time.Duration(index) * time.Minute),
			"recScore": float64(100 - index), "sourceOwner": "qwq_data",
			"supplySource": "data_engineering", "releaseId": releaseID,
			"manifestDigest": digest, "lifecycleStatus": "active",
		})
	}
	cleanupIDs := append([]string(nil), oldIDs...)
	cleanupIDs = append(cleanupIDs, "ranked-window-api-live-replacement")
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"postId": bson.M{"$in": cleanupIDs}})
	})
	_, _ = collection.DeleteMany(ctx, bson.M{"postId": bson.M{"$in": cleanupIDs}})
	if _, err := collection.InsertMany(ctx, documents); err != nil {
		t.Fatalf("seed initial Mongo ranked candidates: %v", err)
	}

	engine := rtrec.NewEngine(
		rtrec.NewHotPath(rtredis.NewRecAdapter(requireTestRouter(t).Scene("rec"))),
		[]rtrec.CandidateSource{recinfra.NewMongoCandidateSource(requireMongoDB(t))},
	)
	request := rtrec.GetFeedRequest{
		UserID: "ranked-window-api-actor", PersonaID: "ranked-window-api-persona",
		SessionID: "ranked-window-api-session", FeedType: rtrec.FeedDiscovery,
		RankedWindowSubjectID: "actor\x00ranked-window-api-actor",
		Sort:                  rtrec.FeedSortRecommend, Surface: "home", ChannelID: "recommend",
		FeedRequestID: "frq_ranked_window_api", ActiveReleaseID: releaseID,
		ActiveManifestDigest: digest, Limit: 2, DeferDeliveryAccounting: true,
	}
	first, err := engine.GetFeed(ctx, request)
	if err != nil {
		t.Fatalf("create ranked feed window: %v", err)
	}
	if first.NextContinuation == nil {
		t.Fatalf("first page did not create real-Redis continuation: %+v", first)
	}
	request.Continuation = first.NextContinuation
	pageBeforeMutation, err := engine.GetFeed(ctx, request)
	if err != nil || len(pageBeforeMutation.Items) == 0 {
		t.Fatalf("load continuation before Mongo mutation: response=%+v err=%v", pageBeforeMutation, err)
	}

	if _, err := collection.DeleteMany(ctx, bson.M{"postId": bson.M{"$in": oldIDs}}); err != nil {
		t.Fatalf("remove original live candidates: %v", err)
	}
	if _, err := collection.InsertOne(ctx, bson.M{
		"postId": "ranked-window-api-live-replacement", "contentType": "image",
		"authorId": "ranked-window-api-live-author", "status": "published",
		"visibility": "public", "publishedAt": now.Add(time.Hour), "recScore": 10000.0,
		"sourceOwner": "qwq_data", "supplySource": "data_engineering",
		"releaseId": releaseID, "manifestDigest": digest, "lifecycleStatus": "active",
	}); err != nil {
		t.Fatalf("seed replacement live candidate: %v", err)
	}

	pageAfterMutation, err := engine.GetFeed(ctx, request)
	if err != nil {
		t.Fatalf("continue immutable real-Redis window after Mongo mutation: %v", err)
	}
	if len(pageAfterMutation.Items) != len(pageBeforeMutation.Items) {
		t.Fatalf("continuation size drifted after live mutation: before=%+v after=%+v", pageBeforeMutation.Items, pageAfterMutation.Items)
	}
	for index := range pageBeforeMutation.Items {
		before := pageBeforeMutation.Items[index]
		after := pageAfterMutation.Items[index]
		if after.ContentID != before.ContentID || after.ContentID == "ranked-window-api-live-replacement" {
			t.Fatalf("continuation order drifted at %d: before=%+v after=%+v", index, before, after)
		}
	}
}

func TestRankedFeedWindowRealRedisNinthWindowEvictsFirstPerSubject(t *testing.T) {
	ctx := context.Background()
	const (
		releaseID = "rel_ranked_window_quota_api"
		digest    = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	)
	candidates := make([]rtrec.ContentCandidate, 0, 3)
	for index := 0; index < 3; index++ {
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID:       fmt.Sprintf("ranked-window-quota-api-%02d", index),
			ContentType:     "image",
			AuthorID:        fmt.Sprintf("ranked-window-quota-author-%02d", index),
			SourceOwner:     "qwq_data",
			SupplySource:    "data_engineering",
			ReleaseID:       releaseID,
			ManifestDigest:  digest,
			LifecycleStatus: "active",
		})
	}
	engine := rtrec.NewEngine(
		rtrec.NewHotPath(rtredis.NewRecAdapter(requireTestRouter(t).Scene("rec"))),
		[]rtrec.CandidateSource{rankedWindowStaticSource{candidates: candidates}},
	)
	createFirstPage := func(actorID string, sequence int) (rtrec.GetFeedRequest, *rtrec.RankedFeedContinuation) {
		t.Helper()
		request := rtrec.GetFeedRequest{
			UserID: actorID, PersonaID: actorID + "-persona",
			SessionID:             fmt.Sprintf("%s-session-%02d", actorID, sequence),
			RankedWindowSubjectID: "actor\x00" + actorID,
			FeedType:              rtrec.FeedDiscovery, Sort: rtrec.FeedSortRecommend,
			Surface: "home", ChannelID: "recommend",
			FeedRequestID:   fmt.Sprintf("frq_%s_%02d", actorID, sequence),
			ActiveReleaseID: releaseID, ActiveManifestDigest: digest,
			Limit: 1, DeferDeliveryAccounting: true,
		}
		response, err := engine.GetFeed(ctx, request)
		if err != nil || response.NextContinuation == nil {
			t.Fatalf("create actor=%s sequence=%d window: response=%+v err=%v", actorID, sequence, response, err)
		}
		return request, response.NextContinuation
	}

	otherRequest, otherContinuation := createFirstPage("ranked-window-quota-other", 0)
	var firstRequest rtrec.GetFeedRequest
	var firstContinuation *rtrec.RankedFeedContinuation
	var ninthRequest rtrec.GetFeedRequest
	var ninthContinuation *rtrec.RankedFeedContinuation
	for sequence := 0; sequence < rtrec.RankedFeedWindowMaxActivePerSubject+1; sequence++ {
		request, continuation := createFirstPage("ranked-window-quota-primary", sequence)
		if sequence == 0 {
			firstRequest = request
			firstContinuation = continuation
		}
		if sequence == rtrec.RankedFeedWindowMaxActivePerSubject {
			ninthRequest = request
			ninthContinuation = continuation
		}
	}

	firstRequest.Continuation = firstContinuation
	if _, err := engine.GetFeed(ctx, firstRequest); !errors.Is(err, rtrec.ErrInvalidFeedCursor) {
		t.Fatalf("first of nine real-Redis windows error=%v, want ErrInvalidFeedCursor", err)
	}
	ninthRequest.Continuation = ninthContinuation
	if _, err := engine.GetFeed(ctx, ninthRequest); err != nil {
		t.Fatalf("ninth real-Redis window was not retained: %v", err)
	}
	otherRequest.Continuation = otherContinuation
	if _, err := engine.GetFeed(ctx, otherRequest); err != nil {
		t.Fatalf("primary subject quota crossed subject isolation: %v", err)
	}
}

func TestRankedFeedWindowRealRedisKeepsAnonymousSessionsIsolated(t *testing.T) {
	ctx := context.Background()
	const (
		releaseID = "rel_ranked_window_anonymous_api"
		digest    = "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
	)
	candidates := []rtrec.ContentCandidate{
		{ContentID: "anonymous-window-api-1", ContentType: "image", AuthorID: "anonymous-author-api-1", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "anonymous-window-api-2", ContentType: "video", AuthorID: "anonymous-author-api-2", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
		{ContentID: "anonymous-window-api-3", ContentType: "article", AuthorID: "anonymous-author-api-3", SourceOwner: "qwq_data", SupplySource: "data_engineering", ReleaseID: releaseID, ManifestDigest: digest, LifecycleStatus: "active"},
	}
	engine := rtrec.NewEngine(
		rtrec.NewHotPath(rtredis.NewRecAdapter(requireTestRouter(t).Scene("rec"))),
		[]rtrec.CandidateSource{rankedWindowStaticSource{candidates: candidates}},
	)
	testRun := fmt.Sprintf("%d", time.Now().UnixNano())
	firstSessionID := "anonymous-window-session-a-" + testRun
	secondSessionID := "anonymous-window-session-b-" + testRun
	createFirstPage := func(sessionID string, sequence int) (rtrec.GetFeedRequest, *rtrec.RankedFeedContinuation) {
		t.Helper()
		request := rtrec.GetFeedRequest{
			UserID:    identity.AnonymousFallbackPersonaID,
			SessionID: sessionID,
			RankedWindowSubjectID: identity.RankedFeedWindowSubjectID(
				identity.AnonymousFallbackPersonaID,
				sessionID,
			),
			FeedType: rtrec.FeedDiscovery, Sort: rtrec.FeedSortRecommend,
			Surface: "home", ChannelID: "recommend",
			FeedRequestID:   fmt.Sprintf("frq_anonymous_%s_%02d", testRun, sequence),
			ActiveReleaseID: releaseID, ActiveManifestDigest: digest,
			Limit: 1, DeferDeliveryAccounting: true,
		}
		response, err := engine.GetFeed(ctx, request)
		if err != nil || response.NextContinuation == nil {
			t.Fatalf("create anonymous session=%s sequence=%d window: response=%+v err=%v", sessionID, sequence, response, err)
		}
		return request, response.NextContinuation
	}

	var firstRequest rtrec.GetFeedRequest
	var firstContinuation *rtrec.RankedFeedContinuation
	for sequence := 0; sequence < rtrec.RankedFeedWindowMaxActivePerSubject; sequence++ {
		request, continuation := createFirstPage(firstSessionID, sequence)
		if sequence == 0 {
			firstRequest = request
			firstContinuation = continuation
		}
	}
	_, _ = createFirstPage(secondSessionID, rtrec.RankedFeedWindowMaxActivePerSubject)

	firstRequest.Continuation = firstContinuation
	if _, err := engine.GetFeed(ctx, firstRequest); err != nil {
		t.Fatalf("anonymous session B evicted session A's real-Redis continuation: %v", err)
	}
}
