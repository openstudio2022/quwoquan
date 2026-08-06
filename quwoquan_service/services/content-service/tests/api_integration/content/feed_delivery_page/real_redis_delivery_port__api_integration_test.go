// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
// readiness_case: append-feed-delivery-page-api
package feed_delivery_page_test

import (
	"context"
	"errors"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
	deliverypost "quwoquan_service/services/content-service/internal/content/feed_delivery_page/adapters/inbound/post"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
)

func TestDeliveryPortPersistsImmutableBoundedPageInRealRedis(t *testing.T) {
	runtime, err := testinfra.StartRealRedis(context.Background())
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := runtime.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     runtime.Addr,
				Password: runtime.Password,
				DB:       0,
				TLS:      runtime.TLS,
			},
			"rec": {
				Mode:     "standalone",
				Addr:     runtime.Addr,
				Password: runtime.Password,
				DB:       0,
				TLS:      runtime.TLS,
			},
			"realtime": {
				Mode:     "standalone",
				Addr:     runtime.Addr,
				Password: runtime.Password,
				DB:       0,
				TLS:      runtime.TLS,
			},
		},
		PrefixRoutes: rtredis.DefaultRouterConfig().PrefixRoutes,
		DefaultScene: "rec",
	})
	t.Cleanup(func() {
		if closeErr := router.Close(); closeErr != nil {
			t.Errorf("close Redis router: %v", closeErr)
		}
	})
	port := deliverypost.NewDeliveryPort(deliveryredis.NewStore(router.Scene("rec")))

	pageID, err := deliverymodel.NewID()
	if err != nil {
		t.Fatalf("new delivery page identity: %v", err)
	}
	createdAt := time.Now().UTC()
	page := deliverymodel.Page{
		DeliveryPageID: pageID,
		ScopeHash:      deliverymodel.ScopeHash("persona\x00session\x00feed\x0020"),
		FeedRequestID:  "feed-request-real-redis",
		PageSize:       20,
		Depth:          0,
		Items: []deliverymodel.PostReference{
			{PostID: "post-delivered", RecallPath: "candidate_index"},
		},
		ReleaseID:      "release-canonical",
		ManifestDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		PolicyDigest:   "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
		CreatedAt:      createdAt,
		ExpiresAt:      createdAt.Add(deliverymodel.TTL),
	}
	first, err := port.Append(context.Background(), page)
	if err != nil || first.DeliveryPageID != pageID {
		t.Fatalf("append FeedDeliveryPage page=%#v err=%v", first, err)
	}
	replayed, err := port.Append(context.Background(), page)
	if err != nil || replayed.DeliveryPageID != pageID {
		t.Fatalf("replay FeedDeliveryPage page=%#v err=%v", replayed, err)
	}
	loaded, err := port.Load(context.Background(), page.ScopeHash, pageID)
	if err != nil || len(loaded.Items) != 1 || loaded.Items[0].PostID != "post-delivered" {
		t.Fatalf("load FeedDeliveryPage page=%#v err=%v", loaded, err)
	}
	conflict := page
	conflict.Items = []deliverymodel.PostReference{{PostID: "post-different"}}
	if _, err := port.Append(context.Background(), conflict); !errors.Is(err, deliveryapp.ErrConflict) {
		t.Fatalf("conflicting immutable page error=%v want=%v", err, deliveryapp.ErrConflict)
	}
}
