// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-002.t3
package assistant_task_view_test

import (
	"context"
	"errors"
	"testing"
	"time"

	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	tasksource "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/infrastructure/source"
	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

type subscriptionReaderStub struct {
	items  []subscriptionmodel.SkillSubscription
	status string
	err    error
}

func (reader *subscriptionReaderStub) ListSkillSubscriptions(
	_ context.Context,
	_ string,
	status string,
	_ int,
) ([]subscriptionmodel.SkillSubscription, error) {
	reader.status = status
	if reader.err != nil || status == "" {
		return append([]subscriptionmodel.SkillSubscription(nil), reader.items...), reader.err
	}
	items := make([]subscriptionmodel.SkillSubscription, 0, len(reader.items))
	for _, item := range reader.items {
		if item.Status == status {
			items = append(items, item)
		}
	}
	return items, nil
}

type catalogReaderStub struct {
	items []catalogmodel.Item
	err   error
}

func (reader catalogReaderStub) ListSkills(
	_ context.Context,
	_ catalogapplication.ListSkillsQuery,
) (catalogmodel.ListView, error) {
	return catalogmodel.ListView{Items: append([]catalogmodel.Item(nil), reader.items...)}, reader.err
}

func TestSubscriptionTaskReaderMapsOwnerStateAndActiveCatalog(t *testing.T) {
	now := time.Date(2026, 8, 10, 3, 0, 0, 0, time.UTC)
	next := now.Add(time.Hour)
	subscriptions := &subscriptionReaderStub{items: []subscriptionmodel.SkillSubscription{
		{
			SubscriptionID: "subscription-paused",
			Owner: subscriptionmodel.SkillSubscriptionOwner{
				OwnerType: "user", OwnerID: "account-1",
			},
			SkillID: "news_briefing", Status: subscriptionmodel.SkillSubscriptionStatusPaused,
			DeliveryState: subscriptionmodel.SkillSubscriptionDeliveryState{NextAttemptAt: &next},
			UpdatedAt:     now.Add(-time.Minute),
		},
		{
			SubscriptionID: "subscription-active",
			Owner: subscriptionmodel.SkillSubscriptionOwner{
				OwnerType: "user", OwnerID: "account-1",
			},
			SkillID: "travel_companion", Status: subscriptionmodel.SkillSubscriptionStatusActive,
			DeliveryState: subscriptionmodel.SkillSubscriptionDeliveryState{NextAttemptAt: &next},
			UpdatedAt:     now,
		},
	}}
	reader := tasksource.NewSubscriptionTaskReader(
		subscriptions,
		catalogReaderStub{items: []catalogmodel.Item{
			{SkillID: "travel_companion", DisplayName: "贴身旅行管家", Description: "行程提醒"},
			{SkillID: "news_briefing", DisplayName: "每日新闻简报", Description: "每日摘要"},
		}},
	)

	items, err := reader.List(t.Context(), "account-1", "", 20)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 2 || items[0].TaskID != "subscription-active" ||
		items[0].Title != "贴身旅行管家" || items[0].Status != "in_progress" ||
		items[0].DueAt == nil || items[1].Status != "pending" || items[1].DueAt != nil {
		t.Fatalf("unexpected federated tasks: %+v", items)
	}

	filtered, err := reader.List(t.Context(), "account-1", "completed", 20)
	if err != nil {
		t.Fatal(err)
	}
	if subscriptions.status != subscriptionmodel.SkillSubscriptionStatusArchived || len(filtered) != 0 {
		t.Fatalf("subscription filter=%q items=%+v", subscriptions.status, filtered)
	}
	unknown, err := reader.List(t.Context(), "account-1", "active", 20)
	if err != nil || len(unknown) != 0 {
		t.Fatalf("noncanonical task status returned items=%+v err=%v", unknown, err)
	}
}

func TestSubscriptionTaskReaderFailsClosedOnOwnerOrCatalogDrift(t *testing.T) {
	now := time.Date(2026, 8, 10, 3, 0, 0, 0, time.UTC)
	base := subscriptionmodel.SkillSubscription{
		SubscriptionID: "subscription-1",
		Owner: subscriptionmodel.SkillSubscriptionOwner{
			OwnerType: "user", OwnerID: "account-other",
		},
		SkillID: "travel_companion", Status: subscriptionmodel.SkillSubscriptionStatusActive,
		UpdatedAt: now,
	}
	reader := tasksource.NewSubscriptionTaskReader(
		&subscriptionReaderStub{items: []subscriptionmodel.SkillSubscription{base}},
		catalogReaderStub{items: []catalogmodel.Item{{
			SkillID: "travel_companion", DisplayName: "贴身旅行管家",
		}}},
	)
	if _, err := reader.List(t.Context(), "account-1", "", 20); !errors.Is(err, taskapplication.ErrProjectionUnavailable) {
		t.Fatalf("owner drift returned %v", err)
	}

	base.Owner.OwnerID = "account-1"
	missingCatalog := tasksource.NewSubscriptionTaskReader(
		&subscriptionReaderStub{items: []subscriptionmodel.SkillSubscription{base}},
		catalogReaderStub{},
	)
	if _, err := missingCatalog.List(t.Context(), "account-1", "", 20); !errors.Is(err, taskapplication.ErrProjectionUnavailable) {
		t.Fatalf("missing catalog returned %v", err)
	}
}
