package source

import (
	"context"
	"errors"
	"sort"
	"strings"

	taskapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/application"
	taskmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_task_view/domain/model"
	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

const maximumTaskSourceItems = 100

type SubscriptionReader interface {
	ListSkillSubscriptions(
		context.Context,
		string,
		string,
		int,
	) ([]subscriptionmodel.SkillSubscription, error)
}

type CatalogReader interface {
	ListSkills(
		context.Context,
		catalogapplication.ListSkillsQuery,
	) (catalogmodel.ListView, error)
}

// SubscriptionTaskReader federates owner subscription state with the active,
// digest-verified Skill catalog. It deliberately has no task collection or
// fallback title: returning a raw skill ID would expose a package identity as
// product copy and would let a retired catalog entry survive in the UI.
type SubscriptionTaskReader struct {
	subscriptions SubscriptionReader
	catalog       CatalogReader
}

var _ taskapplication.Reader = (*SubscriptionTaskReader)(nil)

func NewSubscriptionTaskReader(
	subscriptions SubscriptionReader,
	catalog CatalogReader,
) *SubscriptionTaskReader {
	return &SubscriptionTaskReader{
		subscriptions: subscriptions,
		catalog:       catalog,
	}
}

func (reader *SubscriptionTaskReader) List(
	ctx context.Context,
	accountID string,
	taskStatus string,
	limit int,
) ([]taskmodel.Item, error) {
	accountID = strings.TrimSpace(accountID)
	if reader == nil || reader.subscriptions == nil || reader.catalog == nil ||
		accountID == "" {
		return nil, taskapplication.ErrProjectionUnavailable
	}
	if limit <= 0 || limit > maximumTaskSourceItems {
		limit = maximumTaskSourceItems
	}
	subscriptionStatus, supported := subscriptionStatusForTask(taskStatus)
	if !supported {
		return []taskmodel.Item{}, nil
	}
	subscriptions, err := reader.subscriptions.ListSkillSubscriptions(
		ctx,
		accountID,
		subscriptionStatus,
		limit,
	)
	if err != nil {
		return nil, errors.Join(taskapplication.ErrProjectionUnavailable, err)
	}
	catalog, err := reader.catalog.ListSkills(ctx, catalogapplication.ListSkillsQuery{
		AccountID: accountID,
		Limit:     maximumTaskSourceItems,
	})
	if err != nil {
		return nil, errors.Join(taskapplication.ErrProjectionUnavailable, err)
	}
	catalogBySkill := make(map[string]catalogmodel.Item, len(catalog.Items))
	for _, item := range catalog.Items {
		skillID := strings.TrimSpace(item.SkillID)
		if skillID == "" || strings.TrimSpace(item.DisplayName) == "" {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		if _, duplicate := catalogBySkill[skillID]; duplicate {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		catalogBySkill[skillID] = item
	}

	items := make([]taskmodel.Item, 0, len(subscriptions))
	seen := make(map[string]struct{}, len(subscriptions))
	for _, subscription := range subscriptions {
		if subscription.Owner.OwnerType != "user" ||
			strings.TrimSpace(subscription.Owner.OwnerID) != accountID ||
			strings.TrimSpace(subscription.SubscriptionID) == "" ||
			subscription.UpdatedAt.IsZero() {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		if _, duplicate := seen[subscription.SubscriptionID]; duplicate {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		seen[subscription.SubscriptionID] = struct{}{}
		catalogItem, found := catalogBySkill[strings.TrimSpace(subscription.SkillID)]
		if !found {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		status, statusErr := taskStatusForSubscription(subscription.Status)
		if statusErr != nil {
			return nil, taskapplication.ErrProjectionUnavailable
		}
		var dueAt = subscription.DeliveryState.NextAttemptAt
		if status != "in_progress" {
			dueAt = nil
		}
		items = append(items, taskmodel.Item{
			AccountID:     accountID,
			TaskID:        subscription.SubscriptionID,
			Title:         strings.TrimSpace(catalogItem.DisplayName),
			Description:   strings.TrimSpace(catalogItem.Description),
			Status:        status,
			DueAt:         dueAt,
			SourceSkillID: strings.TrimSpace(subscription.SkillID),
			UpdatedAt:     subscription.UpdatedAt.UTC(),
		})
	}
	sort.Slice(items, func(left, right int) bool {
		if items[left].UpdatedAt.Equal(items[right].UpdatedAt) {
			return items[left].TaskID < items[right].TaskID
		}
		return items[left].UpdatedAt.After(items[right].UpdatedAt)
	})
	return items, nil
}

func subscriptionStatusForTask(status string) (string, bool) {
	switch strings.TrimSpace(status) {
	case "":
		return "", true
	case "in_progress":
		return subscriptionmodel.SkillSubscriptionStatusActive, true
	case "pending":
		return subscriptionmodel.SkillSubscriptionStatusPaused, true
	case "completed":
		return subscriptionmodel.SkillSubscriptionStatusArchived, true
	default:
		return "", false
	}
}

func taskStatusForSubscription(status string) (string, error) {
	switch strings.TrimSpace(status) {
	case subscriptionmodel.SkillSubscriptionStatusActive:
		return "in_progress", nil
	case subscriptionmodel.SkillSubscriptionStatusPaused:
		return "pending", nil
	case subscriptionmodel.SkillSubscriptionStatusArchived:
		return "completed", nil
	default:
		return "", subscriptionmodel.ErrInvalidStatus
	}
}
