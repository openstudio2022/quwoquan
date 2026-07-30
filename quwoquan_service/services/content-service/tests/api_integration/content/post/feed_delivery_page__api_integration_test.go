// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
package api_integration

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/boundedrecord"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
	feedapp "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

func TestFeedDeliveryPageRealRedisGlobalShardAdmissionDoesNotEvictOtherScope(
	t *testing.T,
) {
	ctx := context.Background()
	policy := boundedrecord.Policy{
		ShardCount:                 4096,
		MaximumLiveRecordsPerShard: 2,
		MaximumLiveBytesPerShard:   1 << 20,
		MaximumLiveRecordsPerOwner: 2,
	}
	scopes, shard := collidingDeliveryPageScopes(t, policy, 3)
	tag := "{fdp-" + shard + "}"
	indexKey := "rec:feed_delivery_page_index:" + tag
	metadataKey := "rec:feed_delivery_page_metadata:" + tag
	recClient := requireTestRouter(t).Scene("rec")
	if err := recClient.Del(ctx, indexKey, metadataKey); err != nil {
		t.Fatalf("clear isolated delivery quota shard: %v", err)
	}
	t.Cleanup(func() {
		_ = recClient.Del(context.Background(), indexKey, metadataKey)
	})
	now := time.Now().UTC().Truncate(time.Millisecond)
	store := deliveryredis.NewStore(
		recClient,
		deliveryredis.WithClock(func() time.Time { return now }),
		deliveryredis.WithQuotaPolicy(policy),
	)
	pages := make([]deliverymodel.Page, 0, len(scopes))
	for index, scopeHash := range scopes {
		pageID, err := deliverymodel.NewID()
		if err != nil {
			t.Fatalf("new delivery quota page id: %v", err)
		}
		page := deliverymodel.Page{
			DeliveryPageID: pageID,
			ScopeHash:      scopeHash,
			FeedRequestID:  fmt.Sprintf("frq_delivery_global_quota_%d", index),
			PageSize:       1,
			Items:          []deliverymodel.PostReference{{PostID: fmt.Sprintf("quota-post-%d", index)}},
			OutboundCursor: fmt.Sprintf("fc.quota.%d", index),
			CreatedAt:      now,
			ExpiresAt:      now.Add(deliverymodel.TTL),
		}
		pages = append(pages, page)
		_, appendErr := store.Append(ctx, page)
		if index < 2 {
			if appendErr != nil {
				t.Fatalf("seed delivery quota scope %d: %v", index, appendErr)
			}
			valueKey := fmt.Sprintf(
				"rec:feed_delivery_page:%s:%s:%s",
				tag,
				scopeHash,
				pageID,
			)
			t.Cleanup(func() {
				_ = recClient.Del(context.Background(), valueKey)
			})
			continue
		}
		if !errors.Is(appendErr, deliveryapp.ErrShardKeyQuota) {
			t.Fatalf(
				"delivery global quota error=%v, want ErrShardKeyQuota",
				appendErr,
			)
		}
	}
	for _, page := range pages[:2] {
		if _, err := store.Load(ctx, page.ScopeHash, page.DeliveryPageID); err != nil {
			t.Fatalf("rejected scope evicted admitted page: %v", err)
		}
	}
}

func collidingDeliveryPageScopes(
	t *testing.T,
	policy boundedrecord.Policy,
	count int,
) ([]string, string) {
	t.Helper()
	byShard := make(map[string][]string)
	for index := 0; index < 100000; index++ {
		scopeHash := deliverymodel.ScopeHash(
			fmt.Sprintf("delivery-quota-collision-%d", index),
		)
		shard, err := policy.ShardForDigest(scopeHash)
		if err != nil {
			t.Fatalf("map delivery quota scope: %v", err)
		}
		if shard <= "00ff" {
			continue
		}
		byShard[shard] = append(byShard[shard], scopeHash)
		if len(byShard[shard]) == count {
			return byShard[shard], shard
		}
	}
	t.Fatalf("find %d delivery scopes in one isolated quota shard", count)
	return nil, ""
}

// TestFeedDeliveryPageRoundTripsThroughMongoAndRealRedis proves the production
// Post reader and rec-scene Redis adapter participate in one bidirectional page
// contract. A previous cursor rehydrates only the immutable delivered identity;
// it never issues a reverse timeline query or substitutes a newer live Post.
func TestFeedDeliveryPageRoundTripsThroughMongoAndRealRedis(t *testing.T) {
	ctx := context.Background()
	run := fmt.Sprintf("%d", time.Now().UnixNano())
	ids := []string{
		"delivery-page-api-first-" + run,
		"delivery-page-api-second-" + run,
		"delivery-page-api-third-" + run,
		"delivery-page-api-live-replacement-" + run,
	}
	collection := requireMongoDB(t).Collection("posts")
	t.Cleanup(func() {
		_, _ = collection.DeleteMany(context.Background(), bson.M{"_id": bson.M{"$in": ids}})
	})
	now := time.Now().UTC().Add(24 * time.Hour)
	documents := make([]any, 0, 3)
	for index, id := range ids[:3] {
		createdAt := now.Add(-time.Duration(index) * time.Minute)
		documents = append(documents, bson.M{
			"_id": id, "authorId": "delivery-page-api-author-" + run,
			"contentType": "image", "contentIdentity": "work",
			"status": "published", "visibility": "public", "moderationStatus": "approved",
			"createdAt": createdAt, "publishedAt": createdAt,
		})
	}
	if _, err := collection.InsertMany(ctx, documents); err != nil {
		t.Fatalf("seed delivered pages: %v", err)
	}

	request := feedapp.ListFeedRequest{
		SessionID: "delivery-page-api-session-" + run,
		Identity:  "work",
		Type:      "image",
		Limit:     1,
	}
	first, err := testFeedService.ListFeed(ctx, request)
	if err != nil || len(first.Items) != 1 || first.Items[0].PostID != ids[0] || first.NextCursor == "" {
		t.Fatalf("first page=%+v err=%v", first, err)
	}
	request.Cursor = first.NextCursor
	request.FeedRequestID = first.FeedRequestID
	second, err := testFeedService.ListFeed(ctx, request)
	if err != nil || len(second.Items) != 1 || second.Items[0].PostID != ids[1] || second.PreviousCursor == "" {
		t.Fatalf("second page=%+v err=%v", second, err)
	}

	if _, err := collection.InsertOne(ctx, bson.M{
		"_id": ids[3], "authorId": "delivery-page-api-replacement-author-" + run,
		"contentType": "image", "contentIdentity": "work",
		"status": "published", "visibility": "public", "moderationStatus": "approved",
		"createdAt": now.Add(time.Hour), "publishedAt": now.Add(time.Hour),
	}); err != nil {
		t.Fatalf("seed newer live replacement: %v", err)
	}
	request.Cursor = second.PreviousCursor
	replayed, err := testFeedService.ListFeed(ctx, request)
	if err != nil || len(replayed.Items) != 1 || replayed.Items[0].PostID != ids[0] {
		t.Fatalf("real-Redis previous page substituted live data: page=%+v err=%v", replayed, err)
	}
	if replayed.NextCursor != first.NextCursor {
		t.Fatalf("replayed next cursor=%q, want original=%q", replayed.NextCursor, first.NextCursor)
	}

	if _, err := collection.DeleteOne(ctx, bson.M{"_id": ids[0]}); err != nil {
		t.Fatalf("remove originally delivered Post: %v", err)
	}
	empty, err := testFeedService.ListFeed(ctx, request)
	if err != nil {
		t.Fatalf("replay after current-visibility removal: %v", err)
	}
	if len(empty.Items) != 0 {
		t.Fatalf("removed delivered Post was substituted: %+v", empty.Items)
	}
}
