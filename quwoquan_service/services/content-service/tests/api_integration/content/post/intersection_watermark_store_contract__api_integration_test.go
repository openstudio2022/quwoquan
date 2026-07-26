package api_integration

// D·T3 contract：已读水位耐久兜底 rm_intersection_watermark 必须精确往返、$max 单调推进
// （晚到的旧时间戳不回退已推进读位），为「Redis flush/宕机后读位不丢」提供耐久真相源。

import (
	"context"
	"log/slog"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func TestIntersectionWatermarkStore_RoundTripAndMonotonic(t *testing.T) {
	ctx := context.Background()
	db := requireMongoDB(t)
	coll := db.Collection("rm_intersection_watermark")
	_, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^wm_"}})
	t.Cleanup(func() { _, _ = coll.DeleteMany(ctx, bson.M{"_id": bson.M{"$regex": "^wm_"}}) })

	store := recinfra.NewMongoWatermarkStore(db, slog.Default())

	// 空记录读 → 空 map。
	if got, err := store.LoadWatermarks(ctx, "wm_viewer"); err != nil || len(got) != 0 {
		t.Fatalf("empty load: got=%+v err=%v", got, err)
	}

	// 写两维度并回读。
	if err := store.SaveWatermarks(ctx, "wm_viewer", map[string]int64{"identity": 1000, "content": 1000}); err != nil {
		t.Fatalf("save: %v", err)
	}
	got, err := store.LoadWatermarks(ctx, "wm_viewer")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if got["identity"] != 1000 || got["content"] != 1000 {
		t.Fatalf("round-trip mismatch: %+v", got)
	}

	// 推进 identity 到 2000，content 用更旧的 500（必须被 $max 拒绝，保持 1000）。
	if err := store.SaveWatermarks(ctx, "wm_viewer", map[string]int64{"identity": 2000, "content": 500}); err != nil {
		t.Fatalf("save2: %v", err)
	}
	got2, err := store.LoadWatermarks(ctx, "wm_viewer")
	if err != nil {
		t.Fatalf("load2: %v", err)
	}
	if got2["identity"] != 2000 {
		t.Fatalf("identity must advance to 2000, got %d", got2["identity"])
	}
	if got2["content"] != 1000 {
		t.Fatalf("content must stay 1000 ($max rejects older 500), got %d", got2["content"])
	}
}
