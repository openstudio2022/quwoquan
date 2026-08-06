// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
// readiness_case: get-assistant-entry-local
package assistant_entry_view_test

import (
	"context"
	"errors"
	"testing"
	"time"

	entryapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/application"
	entrymodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_entry_view/domain/model"
	pageapplication "quwoquan_service/services/assistant-service/internal/assistant/page_context/application"
	pagemodel "quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type entryReader struct{ view *entrymodel.View }

func (reader entryReader) Get(context.Context, string) (*entrymodel.View, error) {
	return reader.view, nil
}

type pageStore struct{ value *pagemodel.PageContext }

func (store *pageStore) Put(_ context.Context, value pagemodel.PageContext) error {
	store.value = &value
	return nil
}
func (store *pageStore) Get(context.Context, string) (*pagemodel.PageContext, error) {
	return store.value, nil
}

func TestEntryCombinesOneProjectionWithTrustedPageActions(t *testing.T) {
	now := time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
	pages := pageapplication.NewFacade(&pageStore{}, func() time.Time { return now })
	if _, err := pages.Report(t.Context(), "account-1", "persona-1", pagemodel.Snapshot{
		CapturedAt: now, PageType: "article", ConsentGranted: true,
		PageObjects: []pagemodel.ObjectRef{{ObjectTypeRef: "content.Post", ObjectID: "post-1"}},
		UserActions: []pagemodel.Action{},
	}); err != nil {
		t.Fatal(err)
	}
	facade := entryapplication.NewQueryFacade(entryReader{view: &entrymodel.View{
		WelcomeMessage: "欢迎回来", SuggestionLines: []string{"继续上次的话题"},
		Chips: []entrymodel.Chip{}, Actions: []entrymodel.Action{}, Personalized: true,
	}}, pages)
	view, err := facade.GetEntry(t.Context(), "account-1", "article", "post-1")
	if err != nil {
		t.Fatal(err)
	}
	if !view.Personalized || view.WelcomeMessage != "欢迎回来" || len(view.Actions) != 2 {
		t.Fatalf("entry=%+v", view)
	}
	if _, err := facade.GetEntry(t.Context(), "account-1", "article", "post-2"); !errors.Is(err, entryapplication.ErrInvalidPageContext) {
		t.Fatalf("mismatched object error=%v", err)
	}
}

func TestEntryMissingProjectionUsesSameNonPersonalizedContract(t *testing.T) {
	view, err := entryapplication.NewQueryFacade(entryReader{}, nil).
		GetEntry(t.Context(), "account-1", "", "")
	if err != nil {
		t.Fatal(err)
	}
	if view.Personalized || view.WelcomeMessage == "" || len(view.Chips) != 3 || view.Actions == nil {
		t.Fatalf("entry=%+v", view)
	}
}

func TestEntryProjectionDependencyFailsClosed(t *testing.T) {
	_, err := entryapplication.NewQueryFacade(nil, nil).
		GetEntry(t.Context(), "account-1", "", "")
	if !errors.Is(err, entryapplication.ErrProjectionUnavailable) {
		t.Fatalf("unavailable projection dependency returned %v", err)
	}
}
