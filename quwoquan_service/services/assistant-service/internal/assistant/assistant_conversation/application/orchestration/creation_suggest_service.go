package orchestration

import (
	"context"
	"log/slog"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

const creationAssistantSkillID = "creation_assistant"

func (s *AssistantService) SuggestCreationAssistance(ctx context.Context, userID string, input assistant.AssistantCreationSuggestRequest) (_ assistant.AssistantCreationSuggestResponse, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.SuggestCreationAssistance",
		attribute.String("user.id", userID),
		attribute.Int("bound.circle.count", len(input.BoundCircleIDs)))
	defer func() { rtobs.EndSpan(span, err) }()

	userID = strings.TrimSpace(userID)
	if userID == "" {
		return assistant.AssistantCreationSuggestResponse{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if !s.creationAssistantEnabled(ctx, userID) {
		return assistant.AssistantCreationSuggestResponse{
			SuggestedTagRefs:   []string{},
			SuggestedHomepages: []assistant.AssistantSuggestedHomepageView{},
			Available:          false,
			UnavailableReason:  "skill_not_enabled",
		}, nil
	}
	input = normalizeCreationSuggestInput(input)
	if input.DraftTitle == "" && input.DraftSummary == "" && input.BodyDigest == "" && input.PrimaryHomepageID == "" && len(input.BoundCircleIDs) == 0 {
		return assistant.AssistantCreationSuggestResponse{
			SuggestedTagRefs:   []string{},
			SuggestedHomepages: []assistant.AssistantSuggestedHomepageView{},
			Available:          true,
			UnavailableReason:  "empty_draft",
		}, nil
	}
	tagHints := creationTagHints(input)
	if s.creationGrounding == nil {
		return assistant.AssistantCreationSuggestResponse{}, rterr.NewUnavailable(
			rterr.ModuleAssistant,
			"创作辅助暂不可用",
			"creation grounding is not configured",
		)
	}
	tagRefs, err := s.creationGrounding.ResolveTagRefs(ctx, tagHints)
	if err != nil {
		return assistant.AssistantCreationSuggestResponse{}, rterr.NewUnavailable(rterr.ModuleAssistant, "创作辅助暂不可用", err.Error())
	}
	tagRefs = compactStrings(tagRefs)
	homepageIDs := []string{}
	if input.PrimaryHomepageID != "" {
		homepageIDs = append(homepageIDs, input.PrimaryHomepageID)
	}
	homepages, err := s.creationGrounding.ResolveHomepages(ctx, homepageIDs)
	if err != nil {
		return assistant.AssistantCreationSuggestResponse{}, rterr.NewUnavailable(rterr.ModuleAssistant, "创作辅助暂不可用", err.Error())
	}
	homepages = normalizeSuggestedHomepages(homepages)
	return assistant.AssistantCreationSuggestResponse{
		SuggestedTagRefs:   tagRefs,
		SuggestedHomepages: homepages,
		SuggestedTitle:     suggestedCreationTitle(input, homepages),
		SuggestedSummary:   suggestedCreationSummary(input),
		Available:          true,
	}, nil
}

// creationAssistantEnabled 判定创作辅助能力是否已被用户启用。
// fail-closed：store 未装配或查询失败一律视为未启用并结构化告警，
// 禁止"双 store 缺失即放行"或静默吞错误。
func (s *AssistantService) creationAssistantEnabled(ctx context.Context, userID string) bool {
	if s.subscriptions != nil {
		items, err := s.subscriptions.ListSkillSubscriptions(ctx, userID, assistant.SkillSubscriptionStatusActive, 100)
		if err != nil {
			slog.WarnContext(ctx, "assistant creation-suggest subscription lookup failed; treating as disabled",
				slog.String("userId", userID), slog.String("error", err.Error()))
		} else {
			for _, item := range items {
				if strings.TrimSpace(item.SkillID) == creationAssistantSkillID {
					return true
				}
			}
		}
	}
	if s.consents != nil {
		consents, err := s.consents.ListActiveConsents(ctx, userID)
		if err != nil {
			slog.WarnContext(ctx, "assistant creation-suggest consent lookup failed; treating as disabled",
				slog.String("userId", userID), slog.String("error", err.Error()))
		} else {
			for _, consent := range consents {
				if strings.TrimSpace(consent.SkillID) == creationAssistantSkillID || strings.TrimSpace(consent.GrantedScope) == creationAssistantSkillID {
					return true
				}
			}
		}
	}
	return false
}

func normalizeCreationSuggestInput(input assistant.AssistantCreationSuggestRequest) assistant.AssistantCreationSuggestRequest {
	input.DraftTitle = strings.TrimSpace(input.DraftTitle)
	input.DraftSummary = strings.TrimSpace(input.DraftSummary)
	input.BodyDigest = strings.TrimSpace(input.BodyDigest)
	input.PrimaryHomepageID = strings.TrimSpace(input.PrimaryHomepageID)
	input.BoundCircleIDs = compactStrings(input.BoundCircleIDs)
	return input
}

func creationTagHints(input assistant.AssistantCreationSuggestRequest) []string {
	return compactStrings([]string{
		input.DraftTitle,
		input.DraftSummary,
		input.BodyDigest,
	})
}

func normalizeSuggestedHomepages(items []assistant.AssistantSuggestedHomepageView) []assistant.AssistantSuggestedHomepageView {
	out := make([]assistant.AssistantSuggestedHomepageView, 0, len(items))
	seen := map[string]bool{}
	for _, item := range items {
		item.ID = strings.TrimSpace(item.ID)
		item.Type = strings.TrimSpace(item.Type)
		item.CanonicalEntityID = strings.TrimSpace(item.CanonicalEntityID)
		item.DisplayName = strings.TrimSpace(item.DisplayName)
		item.Reason = strings.TrimSpace(item.Reason)
		if item.ID == "" || item.Type == "" || item.DisplayName == "" || seen[item.ID] {
			continue
		}
		seen[item.ID] = true
		out = append(out, item)
	}
	return out
}

func suggestedCreationTitle(
	input assistant.AssistantCreationSuggestRequest,
	homepages []assistant.AssistantSuggestedHomepageView,
) string {
	if input.DraftTitle != "" {
		return ""
	}
	if len(homepages) > 0 {
		return "我和" + homepages[0].DisplayName + "有关的一次发现"
	}
	return ""
}

func suggestedCreationSummary(input assistant.AssistantCreationSuggestRequest) string {
	if input.DraftSummary != "" {
		return ""
	}
	body := input.BodyDigest
	if body == "" {
		body = input.DraftTitle
	}
	if body == "" {
		return ""
	}
	if len([]rune(body)) <= 80 {
		return body
	}
	return string([]rune(body)[:80])
}
