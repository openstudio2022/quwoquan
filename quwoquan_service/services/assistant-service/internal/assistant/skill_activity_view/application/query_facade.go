package application

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/ports"
)

type Source interface {
	ListSkillActivities(context.Context, string, string, int) ([]model.Item, error)
}

type QueryFacade struct {
	sources    []Source
	visibility ports.VisibilityStore
}

func NewQueryFacade(visibility ports.VisibilityStore, sources ...Source) *QueryFacade {
	filtered := make([]Source, 0, len(sources))
	for _, source := range sources {
		if source != nil {
			filtered = append(filtered, source)
		}
	}
	return &QueryFacade{sources: filtered, visibility: visibility}
}

func (facade *QueryFacade) List(
	ctx context.Context,
	accountID, skillID, cursorValue string,
	limit int,
) (model.Slice, error) {
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	if accountID == "" || skillID == "" {
		return model.Slice{}, model.ErrInvalidArgument
	}
	if limit <= 0 {
		limit = 32
	}
	if limit > 100 {
		return model.Slice{}, model.ErrInvalidArgument
	}
	cursor, err := model.ParseCursor(cursorValue)
	if err != nil {
		return model.Slice{}, err
	}
	var hiddenBefore *time.Time
	if facade.visibility != nil {
		hiddenBefore, err = facade.visibility.HiddenBefore(ctx, accountID, skillID)
		if err != nil {
			return model.Slice{}, model.ErrUnavailable
		}
	}
	items := make([]model.Item, 0, limit*len(facade.sources))
	seen := map[string]struct{}{}
	for _, source := range facade.sources {
		fromSource, sourceErr := source.ListSkillActivities(ctx, accountID, skillID, limit+1)
		if sourceErr != nil {
			return model.Slice{}, errors.Join(model.ErrUnavailable, sourceErr)
		}
		for _, item := range fromSource {
			if validateErr := item.Validate(); validateErr != nil ||
				item.AccountID != accountID || item.SkillID != skillID {
				return model.Slice{}, model.ErrUnavailable
			}
			if hiddenBefore != nil && !item.OccurredAt.After(hiddenBefore.UTC()) {
				continue
			}
			if cursor != nil && !beforeCursor(item, *cursor) {
				continue
			}
			if _, duplicate := seen[item.ActivityID]; duplicate {
				continue
			}
			seen[item.ActivityID] = struct{}{}
			items = append(items, item)
		}
	}
	model.Sort(items)
	var nextCursor string
	if len(items) > limit {
		items = items[:limit]
		nextCursor = model.EncodeCursor(items[len(items)-1])
	}
	return model.Slice{
		Items:      items,
		NextCursor: nextCursor,
		ExternalSources: []model.ExternalSource{
			{SourceKind: "connector_connection", OperationRef: "integration.connector_connection.ListConnectorConnections"},
			{SourceKind: "connector_invocation", OperationRef: "integration.connector_invocation.ListConnectorInvocations"},
		},
	}, nil
}

func beforeCursor(item model.Item, cursor model.Cursor) bool {
	if item.OccurredAt.Before(cursor.OccurredAt) {
		return true
	}
	return item.OccurredAt.Equal(cursor.OccurredAt) && item.ActivityID < cursor.ActivityID
}
