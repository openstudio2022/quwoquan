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

type QueryService struct {
	source   ports.CatalogSource
	consents ports.ConsentReader
}

func NewQueryService(
	source ports.CatalogSource,
	consents ports.ConsentReader,
) *QueryService {
	return &QueryService{source: source, consents: consents}
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
	if service.consents == nil {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogConsentUnavailable(
				"skill catalog consent reader is not configured",
			)
	}
	items, sourceErr := service.source.ListCatalogItems(ctx)
	if sourceErr != nil {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogUnavailable(sourceErr.Error())
	}
	grantedScopes, consentErr := service.consents.ListGrantedScopes(ctx, accountID)
	if consentErr != nil {
		return model.ListView{},
			catalogerrors.AppErrorFromSkillCatalogConsentUnavailable(
				consentErr.Error(),
			)
	}

	items = append([]model.Item(nil), items...)
	sort.Slice(items, func(left, right int) bool {
		return items[left].SkillID < items[right].SkillID
	})
	for index := range items {
		if scope := strings.TrimSpace(grantedScopes[items[index].SkillID]); scope != "" {
			items[index].Description += "（已授权：" + scope + "）"
		}
	}
	limit := query.Limit
	if limit > len(items) {
		limit = len(items)
	}
	items = items[:limit]
	span.SetAttributes(attribute.Int("catalog.item_count", len(items)))
	return model.ListView{Items: items}, nil
}
