// L2 契约测试：Post 业务对象 — 缓存命中/失效
package tests

import (
	"context"
	"encoding/json"
	"testing"

	"quwoquan_service/services/content-service/internal/infrastructure/cache"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

func TestCacheFindByID_MissThenHit(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}

	ctx := context.Background()
	innerStore := persistence.NewMongoPostStore(mongoDB.Collection("posts_cache_test"))
	redisClient := testRouter.Scene("general")
	cachedRepo := cache.NewPostCacheRepository(innerStore, redisClient, nil)

	post := &postmodel.Post{
		ID:          "cache_test_01",
		ContentType: "image",
		Status:      "published",
		Visibility:  "public",
	}
	if err := innerStore.Create(ctx, post); err != nil {
		t.Fatalf("seed post: %v", err)
	}
	defer mongoDB.Collection("posts_cache_test").Drop(ctx)

	found, ok := cachedRepo.FindByID(ctx, "cache_test_01")
	if !ok || found == nil {
		t.Fatal("first FindByID (cache miss) should return post")
	}

	cacheKey := "cache:post:cache_test_01"
	data, err := redisClient.GetBytes(ctx, cacheKey)
	if err != nil || len(data) == 0 {
		t.Fatal("post should be cached in Redis after FindByID")
	}

	var cached postmodel.Post
	if err := json.Unmarshal(data, &cached); err != nil {
		t.Fatalf("unmarshal cached data: %v", err)
	}
	if cached.ID != "cache_test_01" {
		t.Errorf("cached ID mismatch: %s", cached.ID)
	}

	found2, ok2 := cachedRepo.FindByID(ctx, "cache_test_01")
	if !ok2 || found2 == nil {
		t.Fatal("second FindByID (cache hit) should return post")
	}
}

func TestCacheInvalidateOnUpdate(t *testing.T) {
	if mongoDB == nil {
		t.Skip("mongo unavailable")
	}

	ctx := context.Background()
	innerStore := persistence.NewMongoPostStore(mongoDB.Collection("posts_cache_inv_test"))
	redisClient := testRouter.Scene("general")
	cachedRepo := cache.NewPostCacheRepository(innerStore, redisClient, nil)

	post := &postmodel.Post{
		ID:          "cache_inv_01",
		ContentType: "micro",
		Body:        "before update",
		Status:      "published",
		Visibility:  "public",
	}
	if err := innerStore.Create(ctx, post); err != nil {
		t.Fatalf("seed post: %v", err)
	}
	defer mongoDB.Collection("posts_cache_inv_test").Drop(ctx)

	cachedRepo.FindByID(ctx, "cache_inv_01")

	post.Body = "after update"
	cachedRepo.Update(ctx, "cache_inv_01", post)

	data, _ := redisClient.GetBytes(ctx, "cache:post:cache_inv_01")
	if len(data) > 0 {
		t.Error("cache should be invalidated after Update")
	}
}
