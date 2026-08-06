// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-001
// readiness_case: append-feed-delivery-page-local
package application_test

import (
	"context"
	"reflect"
	"testing"
	"time"

	deliverypost "quwoquan_service/services/content-service/internal/content/feed_delivery_page/adapters/inbound/post"
	deliverymodel "quwoquan_service/services/content-service/internal/content/feed_delivery_page/domain/model"
)

func TestFeedDeliveryPagePortAppendsAndLoadsOneImmutablePage(t *testing.T) {
	t.Parallel()
	createdAt := time.Now().UTC().Truncate(time.Millisecond)
	deliveryPageID, err := deliverymodel.NewID()
	if err != nil {
		t.Fatalf("create delivery page identity: %v", err)
	}
	page := deliverymodel.Page{
		DeliveryPageID: deliveryPageID,
		ScopeHash:      deliverymodel.ScopeHash("persona:session:/content/feed:20"),
		FeedRequestID:  "feed-request-001",
		PageSize:       1,
		Items:          []deliverymodel.PostReference{{PostID: "post-001"}},
		CreatedAt:      createdAt,
		ExpiresAt:      createdAt.Add(deliverymodel.TTL),
	}
	store := &recordingDeliveryPageStore{}
	port := deliverypost.NewDeliveryPort(store)

	acknowledged, err := port.Append(context.Background(), page)
	if err != nil {
		t.Fatalf("append through Post-facing delivery port: %v", err)
	}
	if store.appendCalls != 1 || acknowledged.DeliveryPageID != page.DeliveryPageID {
		t.Fatalf("append acknowledgement=%+v calls=%d", acknowledged, store.appendCalls)
	}
	loaded, err := port.Load(context.Background(), page.ScopeHash, page.DeliveryPageID)
	if err != nil {
		t.Fatalf("load through Post-facing delivery port: %v", err)
	}
	if store.loadCalls != 1 || !reflect.DeepEqual(loaded, page) {
		t.Fatalf("loaded page=%+v calls=%d", loaded, store.loadCalls)
	}
}

type recordingDeliveryPageStore struct {
	page        deliverymodel.Page
	appendCalls int
	loadCalls   int
}

func (store *recordingDeliveryPageStore) Append(
	_ context.Context,
	page deliverymodel.Page,
) (deliverymodel.Page, error) {
	store.appendCalls++
	store.page = page
	return page, nil
}

func (store *recordingDeliveryPageStore) Load(
	_ context.Context,
	_, _ string,
) (deliverymodel.Page, error) {
	store.loadCalls++
	return store.page, nil
}
