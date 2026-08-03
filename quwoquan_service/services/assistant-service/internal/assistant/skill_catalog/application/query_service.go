package application

import (
	"context"
	"sort"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	catalogerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_catalog"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/ports"
)

type ListSkillsQuery struct {
	AccountID string
	Limit     int
}

type GetSkillCatalogItemQuery struct {
	AccountID string
	SkillID   string
}

type QueryService struct {
	source ports.CatalogSource
}

func NewQueryService(source ports.CatalogSource) *QueryService {
	return &QueryService{source: source}
}

func (service *QueryService) GetSkillCatalogItem(
	ctx context.Context,
	query GetSkillCatalogItemQuery,
) (_ model.DetailView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.skill_catalog.GetSkillCatalogItem",
		attribute.String("skill.id", strings.TrimSpace(query.SkillID)),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(query.AccountID) == "" {
		return model.DetailView{},
			catalogerrors.AppErrorFromSkillCatalogUnauthorized(
				"skill catalog requires a verified account principal",
			)
	}
	skillID := strings.TrimSpace(query.SkillID)
	if skillID == "" {
		return model.DetailView{},
			catalogerrors.AppErrorFromSkillCatalogInvalidArgument(
				"skillId is required",
			)
	}
	if service == nil || service.source == nil {
		return model.DetailView{},
			catalogerrors.AppErrorFromSkillCatalogUnavailable(
				"skill catalog source is not configured",
			)
	}
	items, sourceErr := service.source.ListCatalogItems(ctx)
	if sourceErr != nil {
		return model.DetailView{},
			catalogerrors.AppErrorFromSkillCatalogUnavailable(sourceErr.Error())
	}
	for _, item := range items {
		if item.SkillID != skillID {
			continue
		}
		if len(item.ConfigurationSchema) == 0 {
			return model.DetailView{},
				catalogerrors.AppErrorFromSkillCatalogUnavailable(
					"active Skill configuration schema is unavailable",
				)
		}
		return model.DetailView{
			Item:                item,
			ConfigurationSchema: append([]byte(nil), item.ConfigurationSchema...),
		}, nil
	}
	return model.DetailView{},
		catalogerrors.AppErrorFromSkillCatalogNotFound(
			"active Skill catalog item was not found",
		)
}

func (service *QueryService) ListSkills(
	ctx context.Context,
	query ListSkillsQuery,
) (_ model.ListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.skill_catalog.ListSkills",
		attribute.Int("list.limit", query.Limit),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	accountID := strings.TrimSpace(query.AccountID)
	if accountID == "" {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogUnauthorized(
				"skill catalog requires a verified account principal",
			)
	}
	if query.Limit <= 0 || query.Limit > 100 {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogInvalidArgument(
				"limit must be between 1 and 100",
			)
	}
	if service == nil || service.source == nil {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogUnavailable(
				"skill catalog source is not configured",
			)
	}
	items, sourceErr := service.source.ListCatalogItems(ctx)
	if sourceErr != nil {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogUnavailable(sourceErr.Error())
	}
	items = append([]model.Item(nil), items...)
	sort.Slice(items, func(left, right int) bool {
		return items[left].SkillID < items[right].SkillID
	})
	limit := query.Limit
	if limit > len(items) {
		limit = len(items)
	}
	items = items[:limit]
	span.SetAttributes(attribute.Int("catalog.item_count", len(items)))
	return model.ListView{Items: items}, nil
}
