package feed_delivery_page_redis_test

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/boundedrecord"
	redisruntime "quwoquan_service/runtime/redis"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
	deliveryredis "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/redis"
)

func TestStoreAppendIsImmutableAndLoadDoesNotSlideExpiry(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Millisecond)
	client := redisruntime.NewMemoryClient()
	store := deliveryredis.NewStore(
		client,
		deliveryredis.WithClock(func() time.Time { return now }),
	)
	page := storePageForTest(t, now, 0, "")

	if _, err := store.Append(context.Background(), page); err != nil {
		t.Fatalf("append: %v", err)
	}
	if loaded, err := store.Load(context.Background(), page.ScopeHash, page.DeliveryPageID); err != nil || loaded.DeliveryPageID != page.DeliveryPageID {
		t.Fatalf("load=(%q,%v)", loaded.DeliveryPageID, err)
	}
	shard, err := deliveryredis.DefaultQuotaPolicy().ShardForDigest(page.ScopeHash)
	if err != nil {
		t.Fatalf("derive canonical delivery-page shard: %v", err)
	}
	key := fmt.Sprintf(
		"rec:feed_delivery_page:{fdp-%s}:%s:%s",
		shard,
		page.ScopeHash,
		page.DeliveryPageID,
	)
	raw, err := client.Get(context.Background(), key)
	if err != nil {
		t.Fatalf("read canonical delivery page: %v", err)
	}
	var payload map[string]any
	if err := json.Unmarshal([]byte(raw), &payload); err != nil {
		t.Fatalf("decode canonical delivery page: %v", err)
	}
	if _, exists := payload["version"]; exists {
		t.Fatalf("canonical delivery page retained a schema-version envelope: %s", raw)
	}
	payload["version"] = 1
	versioned, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("encode forbidden version envelope: %v", err)
	}
	if err := client.Set(
		context.Background(),
		key,
		string(versioned),
		deliverymodel.TTL,
	); err != nil {
		t.Fatalf("inject forbidden version envelope: %v", err)
	}
	if _, err := store.Load(
		context.Background(),
		page.ScopeHash,
		page.DeliveryPageID,
	); !errors.Is(err, deliveryapp.ErrNotFound) {
		t.Fatalf("version envelope error=%v, want fail-closed not found", err)
	}
	if err := client.Set(
		context.Background(),
		key,
		raw,
		deliverymodel.TTL,
	); err != nil {
		t.Fatalf("restore canonical delivery page: %v", err)
	}

	conflict := page
	conflict.FeedRequestID = "frq_conflict"
	if _, err := store.Append(context.Background(), conflict); !errors.Is(err, deliveryapp.ErrConflict) {
		t.Fatalf("conflicting append error=%v, want ErrConflict", err)
	}

	now = page.ExpiresAt.Add(time.Nanosecond)
	if _, err := store.Load(context.Background(), page.ScopeHash, page.DeliveryPageID); !errors.Is(err, deliveryapp.ErrNotFound) {
		t.Fatalf("expired load error=%v, want ErrNotFound", err)
	}
}

func TestStoreEnforcesAtomicCapabilityPayloadAndScopeQuota(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Millisecond)
	withoutAtomic := deliveryredis.NewStore(
		clientWithoutAtomicCapability{Client: redisruntime.NewMemoryClient()},
		deliveryredis.WithClock(func() time.Time { return now }),
	)
	if _, err := withoutAtomic.Append(context.Background(), storePageForTest(t, now, 0, "")); !errors.Is(err, deliveryapp.ErrAtomicUnavailable) {
		t.Fatalf("atomic capability error=%v", err)
	}

	store := deliveryredis.NewStore(
		redisruntime.NewMemoryClient(),
		deliveryredis.WithClock(func() time.Time { return now }),
	)
	oversized := storePageForTest(t, now, 0, "")
	oversized.ObjectCards = make([]deliverymodel.ObjectCard, deliverymodel.MaximumObjectCards)
	for index := range oversized.ObjectCards {
		oversized.ObjectCards[index] = deliverymodel.ObjectCard{
			ObjectKind:  "homepage",
			ObjectID:    "homepage-payload-budget-" + strings.Repeat("x", 32),
			Title:       strings.Repeat("t", deliverymodel.MaximumObjectTitleBytes),
			CoverURL:    strings.Repeat("u", deliverymodel.MaximumObjectCoverURLBytes),
			AnchorIndex: 1,
		}
	}
	if _, err := store.Append(context.Background(), oversized); !errors.Is(err, deliveryapp.ErrPayloadTooLarge) {
		t.Fatalf("oversized append error=%v, want ErrPayloadTooLarge", err)
	}

	pages := make([]deliverymodel.Page, 0, deliverymodel.MaximumActivePerScope+1)
	for sequence := 0; sequence <= deliverymodel.MaximumActivePerScope; sequence++ {
		// A scope can own up to eight independently refreshed ranked windows.
		// Use independent depth-zero roots here instead of an impossible cursor
		// chain deeper than MaximumDepth.
		page := storePageForTest(t, now, 0, "")
		if _, err := store.Append(context.Background(), page); err != nil {
			t.Fatalf("append sequence %d: %v", sequence, err)
		}
		pages = append(pages, page)
	}
	if _, err := store.Load(context.Background(), pages[0].ScopeHash, pages[0].DeliveryPageID); !errors.Is(err, deliveryapp.ErrNotFound) {
		t.Fatalf("oldest page error=%v, want quota eviction", err)
	}
	last := pages[len(pages)-1]
	if _, err := store.Load(context.Background(), last.ScopeHash, last.DeliveryPageID); err != nil {
		t.Fatalf("newest page load: %v", err)
	}
}

func TestStoreGlobalShardAdmissionRejectsWithoutCrossScopeEviction(t *testing.T) {
	now := time.Now().UTC().Truncate(time.Millisecond)
	client := redisruntime.NewMemoryClient()
	keyPolicy := boundedrecord.Policy{
		ShardCount:                 1,
		MaximumLiveRecordsPerShard: 2,
		MaximumLiveBytesPerShard:   1 << 20,
		MaximumLiveRecordsPerOwner: 2,
	}
	keyStore := deliveryredis.NewStore(
		client,
		deliveryredis.WithClock(func() time.Time { return now }),
		deliveryredis.WithQuotaPolicy(keyPolicy),
	)
	first := storePageForScope(t, now, "scope-a")
	second := storePageForScope(t, now, "scope-b")
	rejected := storePageForScope(t, now, "scope-c")
	for _, page := range []deliverymodel.Page{first, second} {
		if _, err := keyStore.Append(context.Background(), page); err != nil {
			t.Fatalf("seed scope %q: %v", page.ScopeHash, err)
		}
	}
	if _, err := keyStore.Append(
		context.Background(),
		rejected,
	); !errors.Is(err, deliveryapp.ErrShardKeyQuota) {
		t.Fatalf("global key quota error=%v, want ErrShardKeyQuota", err)
	}
	for _, page := range []deliverymodel.Page{first, second} {
		if _, err := keyStore.Load(
			context.Background(),
			page.ScopeHash,
			page.DeliveryPageID,
		); err != nil {
			t.Fatalf("cross-scope value %q was evicted: %v", page.ScopeHash, err)
		}
	}

	byteFirst := storePageForScope(t, now, "byte-scope-a")
	byteSecond := storePageForScope(t, now, "byte-scope-b")
	firstPayload, err := json.Marshal(byteFirst)
	if err != nil {
		t.Fatalf("marshal first byte-quota page: %v", err)
	}
	secondPayload, err := json.Marshal(byteSecond)
	if err != nil {
		t.Fatalf("marshal second byte-quota page: %v", err)
	}
	byteStore := deliveryredis.NewStore(
		redisruntime.NewMemoryClient(),
		deliveryredis.WithClock(func() time.Time { return now }),
		deliveryredis.WithQuotaPolicy(boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 4,
			MaximumLiveBytesPerShard: int64(
				len(firstPayload) + len(secondPayload) - 1,
			),
			MaximumLiveRecordsPerOwner: 2,
		}),
	)
	if _, err := byteStore.Append(context.Background(), byteFirst); err != nil {
		t.Fatalf("seed byte-quota scope: %v", err)
	}
	if _, err := byteStore.Append(
		context.Background(),
		byteSecond,
	); !errors.Is(err, deliveryapp.ErrShardByteQuota) {
		t.Fatalf("global byte quota error=%v, want ErrShardByteQuota", err)
	}
	if _, err := byteStore.Load(
		context.Background(),
		byteFirst.ScopeHash,
		byteFirst.DeliveryPageID,
	); err != nil {
		t.Fatalf("byte rejection mutated existing scope: %v", err)
	}
}

type clientWithoutAtomicCapability struct {
	redisruntime.Client
}

func storePageForTest(t *testing.T, now time.Time, depth int, previousID string) deliverymodel.Page {
	t.Helper()
	pageID, err := deliverymodel.NewID()
	if err != nil {
		t.Fatalf("new page id: %v", err)
	}
	return deliverymodel.Page{
		DeliveryPageID: pageID,
		ScopeHash:      deliverymodel.ScopeHash("actor/session/route/20"),
		FeedRequestID:  "frq_store_contract",
		PageSize:       deliverymodel.MaximumItems,
		Depth:          depth,
		PreviousPageID: previousID,
		Items:          []deliverymodel.PostReference{{PostID: "post-1"}},
		OutboundCursor: "fc.store-contract",
		CreatedAt:      now,
		ExpiresAt:      now.Add(deliverymodel.TTL),
	}
}

func storePageForScope(
	t *testing.T,
	now time.Time,
	scope string,
) deliverymodel.Page {
	t.Helper()
	page := storePageForTest(t, now, 0, "")
	page.ScopeHash = deliverymodel.ScopeHash(scope)
	return page
}
