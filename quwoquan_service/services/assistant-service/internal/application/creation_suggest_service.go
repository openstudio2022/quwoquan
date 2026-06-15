package application

import (
	"context"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

const creationAssistantSkillID = "creation_assistant"

type CreationSuggestGrounding interface {
	ResolveTagRefs(ctx context.Context, hints []string) ([]string, error)
	ResolveHomepages(ctx context.Context, ids []string) ([]assistant.AssistantSuggestedHomepageView, error)
}

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
	tagRefs := fallbackCreationTagRefs(tagHints)
	homepages := fallbackCreationHomepages(input)
	if s.creationGrounding != nil {
		resolvedTags, err := s.creationGrounding.ResolveTagRefs(ctx, tagHints)
		if err != nil {
			return assistant.AssistantCreationSuggestResponse{}, rterr.NewUnavailable(rterr.ModuleAssistant, "创作辅助暂不可用", err.Error())
		}
		if len(resolvedTags) > 0 {
			tagRefs = compactStrings(resolvedTags)
		}
		homepageIDs := []string{}
		if input.PrimaryHomepageID != "" {
			homepageIDs = append(homepageIDs, input.PrimaryHomepageID)
		}
		resolvedHomepages, err := s.creationGrounding.ResolveHomepages(ctx, homepageIDs)
		if err != nil {
			return assistant.AssistantCreationSuggestResponse{}, rterr.NewUnavailable(rterr.ModuleAssistant, "创作辅助暂不可用", err.Error())
		}
		if len(resolvedHomepages) > 0 {
			homepages = normalizeSuggestedHomepages(resolvedHomepages)
		}
	}
	return assistant.AssistantCreationSuggestResponse{
		SuggestedTagRefs:   tagRefs,
		SuggestedHomepages: homepages,
		SuggestedTitle:     suggestedCreationTitle(input),
		SuggestedSummary:   suggestedCreationSummary(input),
		Available:          true,
	}, nil
}

func (s *AssistantService) creationAssistantEnabled(ctx context.Context, userID string) bool {
	if s.subscriptions != nil {
		items, err := s.subscriptions.ListSkillSubscriptions(ctx, userID, assistant.SkillSubscriptionStatusActive, 100)
		if err == nil {
			for _, item := range items {
				if strings.TrimSpace(item.SkillID) == creationAssistantSkillID {
					return true
				}
			}
		}
	}
	if s.consents != nil {
		consents, err := s.consents.ListActiveConsents(ctx, userID)
		if err == nil {
			for _, consent := range consents {
				if strings.TrimSpace(consent.SkillID) == creationAssistantSkillID || strings.TrimSpace(consent.GrantedScope) == creationAssistantSkillID {
					return true
				}
			}
		}
	}
	return s.subscriptions == nil && s.consents == nil
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
	text := strings.ToLower(input.DraftTitle + " " + input.DraftSummary + " " + input.BodyDigest)
	hints := []string{}
	switch {
	case strings.Contains(text, "九寨") || strings.Contains(text, "旅行") || strings.Contains(text, "徒步") || strings.Contains(text, "路线"):
		hints = append(hints, "Topic/旅行", "Topic/旅行/路线")
	case strings.Contains(text, "ai") || strings.Contains(text, "agent") || strings.Contains(text, "产品"):
		hints = append(hints, "Topic/科技/AI", "Topic/产品")
	case strings.Contains(text, "摄影") || strings.Contains(text, "照片") || strings.Contains(text, "影像"):
		hints = append(hints, "Topic/摄影")
	}
	if input.PrimaryHomepageID != "" {
		hints = append(hints, "Entity/"+input.PrimaryHomepageID)
	}
	return compactStrings(hints)
}

func fallbackCreationTagRefs(hints []string) []string {
	if len(hints) == 0 {
		return []string{}
	}
	return compactStrings(hints)
}

func fallbackCreationHomepages(input assistant.AssistantCreationSuggestRequest) []assistant.AssistantSuggestedHomepageView {
	if input.PrimaryHomepageID == "" {
		return []assistant.AssistantSuggestedHomepageView{}
	}
	return []assistant.AssistantSuggestedHomepageView{{
		ID:                input.PrimaryHomepageID,
		Type:              "homepage",
		DisplayName:       input.PrimaryHomepageID,
		Reason:            "已作为主关联主页",
	}}
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

func suggestedCreationTitle(input assistant.AssistantCreationSuggestRequest) string {
	if input.DraftTitle != "" {
		return ""
	}
	if input.PrimaryHomepageID != "" {
		return "我和" + input.PrimaryHomepageID + "有关的一次发现"
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
