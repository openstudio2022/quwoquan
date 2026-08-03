// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
package page_context_test

import (
	"context"
	"testing"
	"time"

	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type memoryPageStore struct{ value *pagemodel.PageContext }

func (store *memoryPageStore) Put(_ context.Context, value pagemodel.PageContext) error {
	store.value = &value
	return nil
}
func (store *memoryPageStore) Get(context.Context, string) (*pagemodel.PageContext, error) {
	return store.value, nil
}

func TestPageContextHasOneFiveMinuteNonSlidingLifetime(t *testing.T) {
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	store := &memoryPageStore{}
	facade := pageapplication.NewFacade(store, func() time.Time { return now })
	receipt, err := facade.Report(t.Context(), "account-1", "persona-1", pagemodel.Snapshot{
		CapturedAt: now, PageType: "article", ConsentGranted: true,
		PageObjects: []pagemodel.ObjectRef{}, UserActions: []pagemodel.Action{},
	})
	if err != nil {
		t.Fatal(err)
	}
	if receipt.ContextKey != "assistant:page-context:account-1" ||
		!receipt.ExpiresAt.Equal(now.Add(5*time.Minute)) {
		t.Fatalf("receipt=%+v", receipt)
	}
	now = now.Add(4 * time.Minute)
	current, err := facade.Current(t.Context(), "account-1")
	if err != nil || current == nil || !current.ExpiresAt.Equal(receipt.ExpiresAt) {
		t.Fatalf("current=%+v err=%v", current, err)
	}
	now = now.Add(2 * time.Minute)
	current, err = facade.Current(t.Context(), "account-1")
	if err != nil || current != nil {
		t.Fatalf("expired current=%+v err=%v", current, err)
	}
}

func TestPageContextRejectsUntrustedOrUnconsentedSnapshot(t *testing.T) {
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	facade := pageapplication.NewFacade(&memoryPageStore{}, func() time.Time { return now })
	_, err := facade.Report(t.Context(), "account-1", "", pagemodel.Snapshot{
		CapturedAt: now, PageType: "article", ConsentGranted: true,
	})
	if err == nil {
		t.Fatal("missing trusted persona was accepted")
	}
	_, err = facade.Report(t.Context(), "account-1", "persona-1", pagemodel.Snapshot{
		CapturedAt: now, PageType: "article", ConsentGranted: false,
		PageObjects: []pagemodel.ObjectRef{{ObjectTypeRef: "content.Post", ObjectID: "post-1"}},
	})
	if err == nil {
		t.Fatal("unconsented page objects were accepted")
	}
}
