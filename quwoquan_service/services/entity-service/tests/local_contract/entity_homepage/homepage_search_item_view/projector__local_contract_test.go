// spec_ref: specs/feature-tree/shared-homepage-network/homepage-discovery-and-attach/homepage-search-and-picker/spec.md#gwt-001
package local_contract

import (
	"context"
	"testing"
	"time"

	searchitemevent "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/adapters/inbound/event"
	searchitemapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/application"
)

type recordingSearchItemIndex struct {
	upserts []searchitemapp.SearchItem
	deletes []struct {
		id      string
		version int64
	}
}

func (i *recordingSearchItemIndex) UpsertIfNewer(
	_ context.Context,
	item searchitemapp.SearchItem,
) (bool, error) {
	i.upserts = append(i.upserts, item)
	return true, nil
}

func (i *recordingSearchItemIndex) DeleteIfNotOlder(
	_ context.Context,
	id string,
	version int64,
) (bool, error) {
	i.deletes = append(i.deletes, struct {
		id      string
		version int64
	}{id: id, version: version})
	return true, nil
}

func TestHomepageSearchItemViewTypedProjectorOwnsLifecycle(t *testing.T) {
	index := &recordingSearchItemIndex{}
	handler := searchitemevent.NewHandler(searchitemapp.NewProjector(index))
	updatedAt := time.Date(2026, 8, 2, 12, 0, 0, 0, time.UTC)
	applied, err := handler.Apply(context.Background(), searchitemevent.HomepagePublicEvent{
		EventType: "HomepagePublished", HomepageID: "homepage-1",
		EntityID: "entity-1", DisplayName: "苍山主页", EntityType: "sight",
		SourceVersion: 7, UpdatedAt: updatedAt,
	})
	if err != nil || !applied || len(index.upserts) != 1 {
		t.Fatalf("published event not projected: applied=%v upserts=%d err=%v", applied, len(index.upserts), err)
	}
	if index.upserts[0].SourceVersion != 7 || !index.upserts[0].UpdatedAt.Equal(updatedAt) {
		t.Fatalf("projection lost source checkpoint: %+v", index.upserts[0])
	}

	applied, err = handler.Apply(context.Background(), searchitemevent.HomepagePublicEvent{
		EventType: "HomepageRetired", HomepageID: "homepage-1", SourceVersion: 8,
	})
	if err != nil || !applied || len(index.deletes) != 1 || index.deletes[0].version != 8 {
		t.Fatalf("retired event did not create tombstone: applied=%v deletes=%+v err=%v", applied, index.deletes, err)
	}
}

func TestHomepageSearchItemViewRejectsIdentitylessProjection(t *testing.T) {
	handler := searchitemevent.NewHandler(searchitemapp.NewProjector(&recordingSearchItemIndex{}))
	if _, err := handler.Apply(context.Background(), searchitemevent.HomepagePublicEvent{
		EventType: "HomepagePublished", HomepageID: "homepage-1", SourceVersion: 1,
	}); err == nil {
		t.Fatal("published projection without entity identity/display name must fail")
	}
}
