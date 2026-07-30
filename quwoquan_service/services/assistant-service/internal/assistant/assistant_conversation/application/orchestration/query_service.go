package orchestration

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	runerrors "quwoquan_service/services/assistant-service/generated/assistant/assistant_run"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
)

func (s *AssistantService) ReportPageContext(ctx context.Context, userID string, input assistant.PageContextInput) (_ assistant.PageContextAck, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ReportPageContext",
		attribute.String("user.id", userID),
		attribute.String("page.type", input.ContextSnapshot.PageType))
	defer func() { rtobs.EndSpan(span, err) }()

	return s.storePageContext(ctx, userID, input.ContextSnapshot)
}

func (s *AssistantService) GetSuggestedActions(ctx context.Context, userID string, pageType string, objectID string) (_ assistant.SuggestedActionListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetSuggestedActions",
		attribute.String("user.id", userID),
		attribute.String("page.type", pageType))
	defer func() { rtobs.EndSpan(span, err) }()

	pageContextType, parseErr := assistantgenerated.ParseAssistantPageContextType(
		pageType,
	)
	if parseErr != nil ||
		pageContextType == assistantgenerated.AssistantPageContextTypeUnknown {
		return assistant.SuggestedActionListView{},
			runerrors.AppErrorFromRunInvalidArgument(
				"unsupported suggested-actions page type",
			)
	}
	pageType = pageContextType.WireName()
	if err := requireSuggestedActionsPageContext(
		s.loadPageContext(ctx, userID),
		pageContextType,
		objectID,
	); err != nil {
		return assistant.SuggestedActionListView{}, err
	}
	cacheKey := fmt.Sprintf("suggested_actions:%s:%s:%s", fallbackUser(userID), pageType, strings.TrimSpace(objectID))
	if s.cache != nil {
		cached, err := s.cache.Get(ctx, cacheKey)
		if err == nil && strings.TrimSpace(cached) != "" {
			items := parseSuggestedActionCache(cached)
			if len(items) > 0 {
				return assistant.SuggestedActionListView{Items: items}, nil
			}
		}
	}
	items, err := buildSuggestedActions(pageContextType, objectID)
	if err != nil {
		return assistant.SuggestedActionListView{}, err
	}
	if s.learningProjection != nil && strings.TrimSpace(userID) != "" {
		profile, profileErr := s.learningProjection.GetLearningProjection(
			ctx,
			userID,
		)
		if profileErr != nil {
			slog.WarnContext(
				ctx,
				"assistant suggested-actions profile read failed; serving page-context actions",
				slog.String("userId", userID),
				slog.String("error", profileErr.Error()),
			)
		} else if profile != nil {
			if profile.NegativeFeedbackCount > 0 || profile.HighPriorityCount > 0 {
				items = append(items, assistant.SuggestedAction{
					ActionID: "assistant.review_recent_feedback",
					Type:     "review_feedback",
					Label:    "复盘近期反馈",
					Icon:     "thumb_down",
					Payload: suggestedActionPayloadWith(
						map[string]any{"scope": "learning_summary"},
						pageType,
						objectID,
					),
				})
			}
			if metricID, metricScore := selectLowestMetric(profile); metricID != "" && metricScore <= 3 {
				items = append(items, assistant.SuggestedAction{
					ActionID: "assistant.inspect_metric",
					Type:     "inspect_metric",
					Label:    "检查低分指标",
					Icon:     "monitor_heart",
					Payload: suggestedActionPayloadWith(
						map[string]any{
							"metricId": metricID,
							"score":    metricScore,
						},
						pageType,
						objectID,
					),
				})
			}
		}
	}
	if s.cache != nil && len(items) > 0 {
		_ = s.cache.Set(ctx, cacheKey, encodeSuggestedActionCache(items), pageContextTTL)
	}
	return assistant.SuggestedActionListView{Items: dedupeSuggestedActions(items)}, nil
}

func requireSuggestedActionsPageContext(
	snapshot *assistant.AssistantContextSnapshot,
	pageType assistantgenerated.AssistantPageContextType,
	objectID string,
) error {
	if snapshot == nil {
		return runerrors.AppErrorFromRunInvalidArgument(
			"fresh page context is required for suggested actions",
		)
	}
	if snapshot.PageType != pageType.WireName() {
		return runerrors.AppErrorFromRunInvalidArgument(
			"suggested-actions page type does not match stored page context",
		)
	}
	objectID = strings.TrimSpace(objectID)
	if objectID == "" {
		return nil
	}
	for _, pageObject := range snapshot.PageObjects {
		if pageObject.ObjectID == objectID {
			return nil
		}
	}
	return runerrors.AppErrorFromRunInvalidArgument(
		"suggested-actions object id is absent from stored page context",
	)
}

func suggestedActionPayloadWith(
	additional map[string]any,
	pageType string,
	objectID string,
) map[string]any {
	payload := suggestedActionPayload(pageType, objectID)
	for key, value := range additional {
		payload[key] = value
	}
	return payload
}

// GetEntryPersonalization 生成私助半屏入口的欢迎语、建议行与 chips。
// 个性化基于学习画像；画像缺失时返回通用文案（非个性化），画像读取失败
// 只结构化告警并降级为通用文案，不合成"已个性化"的伪状态。
func (s *AssistantService) GetEntryPersonalization(ctx context.Context, userID string, pageType string) (_ assistant.AssistantEntryPersonalizationView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetEntryPersonalization",
		attribute.String("user.id", userID),
		attribute.String("page.type", pageType))
	defer func() { rtobs.EndSpan(span, err) }()

	view := assistant.AssistantEntryPersonalizationView{
		WelcomeMessage: "你好，我是小趣，可以帮你查内容、订阅提醒、整理待办。",
		SuggestionLines: []string{
			"想了解什么？直接问我就行",
		},
		Chips: []assistant.AssistantEntryPersonalizationChipView{
			{ChipID: "chip.search", Label: "帮我搜索", ActionType: "open_search"},
			{ChipID: "chip.skills", Label: "看看技能", ActionType: "open_skill_center"},
			{ChipID: "chip.tasks", Label: "今日待办", ActionType: "open_tasks"},
		},
		Personalized: false,
	}
	if s.learningProjection == nil || strings.TrimSpace(userID) == "" {
		return view, nil
	}
	profile, profileErr := s.learningProjection.GetLearningProjection(ctx, userID)
	if profileErr != nil {
		slog.WarnContext(ctx, "assistant entry personalization profile read failed; serving generic entry",
			slog.String("userId", userID), slog.String("error", profileErr.Error()))
		return view, nil
	}
	if profile == nil {
		return view, nil
	}
	if profile.TotalFeedbackCount > 0 {
		view.Personalized = true
		view.SuggestionLines = append([]string{
			"根据你最近的使用，我可以延续上次的话题继续帮你",
		}, view.SuggestionLines...)
	}
	if profile.NegativeFeedbackCount > 0 {
		view.Chips = append(view.Chips, assistant.AssistantEntryPersonalizationChipView{
			ChipID: "chip.review_feedback", Label: "复盘近期反馈", ActionType: "review_feedback",
		})
	}
	return view, nil
}

func (s *AssistantService) SearchXiaoquResults(ctx context.Context, req assistant.SearchRequest) (_ assistant.AssistantSearchResultView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.SearchXiaoquResults",
		attribute.String("search.intensity", req.SearchIntensity))
	defer func() { rtobs.EndSpan(span, err) }()

	query := strings.TrimSpace(req.UserQuery)
	if query == "" {
		return assistant.AssistantSearchResultView{}, runerrors.AppErrorFromRunInvalidArgument(
			"missing userQuery",
		)
	}
	rawIntensity := strings.ToLower(strings.TrimSpace(req.SearchIntensity))
	if rawIntensity == "" {
		rawIntensity = assistantgenerated.SearchIntensityMedium.WireName()
	}
	intensity, parseErr := assistantgenerated.ParseSearchIntensity(rawIntensity)
	if parseErr != nil {
		return assistant.AssistantSearchResultView{}, runerrors.AppErrorFromRunInvalidArgument(
			fmt.Sprintf("invalid searchIntensity %q", rawIntensity),
		)
	}
	if s.xiaoquSearch == nil {
		return assistant.AssistantSearchResultView{}, rterr.NewUnavailable(
			rterr.ModuleAssistant,
			"小趣搜索暂不可用",
			"xiaoqu search reader is not configured",
		)
	}
	retrieveResp, retrieveErr := s.xiaoquSearch.Retrieve(
		ctx,
		query,
		[]string{"article", "photo", "video", "user", "entity", "circle", "group"},
		8,
	)
	if retrieveErr != nil {
		recordAssistantGroundingOutcome(false)
		return assistant.AssistantSearchResultView{}, rterr.NewUnavailable(
			rterr.ModuleAssistant,
			"小趣搜索暂不可用",
			retrieveErr.Error(),
		)
	}
	citations := make([]assistant.AssistantSearchCitationView, 0, len(retrieveResp.Citations))
	for _, citation := range retrieveResp.Citations {
		target := strings.TrimSpace(citation.ObjectType)
		if target == "" || strings.TrimSpace(citation.ObjectID) == "" {
			continue
		}
		destination, ok := citationDestinationFromSearch(
			target,
			citation.ObjectID,
			citation.URL,
		)
		if !ok {
			continue
		}
		citations = append(citations, assistant.AssistantSearchCitationView{
			CitationID:    citation.CitationID,
			ObjectType:    target,
			ObjectID:      citation.ObjectID,
			Title:         citation.Title,
			Snippet:       citation.Snippet,
			Destination:   destination,
			BadgeLabel:    citation.BadgeLabel,
			SourceDomain:  citation.SourceDomain,
			Score:         citation.Score,
			RecallSource:  retrieveResp.Provenance.Provider,
			ObjectTypeRef: target,
		})
	}
	recordAssistantGroundingOutcome(len(citations) > 0)
	summary := fmt.Sprintf("小趣已通过站内统一检索围绕“%s”找到 %d 条可核验对象线索，可继续追问或打开引用查看。", query, len(citations))
	if len(retrieveResp.DegradeSignals) > 0 && len(retrieveResp.Hits) == 0 {
		summary = retrieveResp.DegradeSignals[0].Message
	}
	return assistant.AssistantSearchResultView{
		QueryEcho:       query,
		Summary:         summary,
		SearchIntensity: intensity.WireName(),
		Citations:       citations,
	}, nil
}

// assistantRetrieveDocuments provides canonical cross-domain candidates feeding
// the unified retrieve pipeline. Each document carries an internal object type
// so TargetForDocument maps it to an AI target (article/entity/group/user);
// callers never see internal types.
func (s *AssistantService) ListAssistantTasks(ctx context.Context, userID string, limit int, status string) (_ assistant.AssistantUserTaskListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListAssistantTasks",
		attribute.String("user.id", userID),
		attribute.String("task.status_filter", status))
	defer func() { rtobs.EndSpan(span, err) }()

	if limit <= 0 {
		limit = 32
	}
	now := s.now()
	items := []assistant.AssistantUserTaskView{}
	if s.learningProjection != nil && strings.TrimSpace(userID) != "" {
		projection, readErr := s.learningProjection.GetLearningProjection(
			ctx,
			userID,
		)
		if readErr != nil {
			slog.WarnContext(ctx, "assistant task projection read failed; returning projected-only list",
				slog.String("userId", userID), slog.String("error", readErr.Error()))
		} else if projection != nil {
			items = append(
				items,
				buildLearningProjectionTasks(projection, now)...,
			)
		}
	}
	// 只返回学习画像投影出的真实待办；无数据即诚实空态，不合成演示任务。
	return assistant.AssistantUserTaskListView{Items: filterTasks(dedupeTasks(items), limit, status)}, nil
}

func buildLearningProjectionTasks(
	projection *learningmodel.LearningProjection,
	now time.Time,
) []assistant.AssistantUserTaskView {
	items := []assistant.AssistantUserTaskView{}
	if projection == nil {
		return items
	}
	if projection.NegativeFeedbackCount > 0 ||
		projection.HighPriorityCount > 0 {
		items = append(items, assistant.AssistantUserTaskView{
			TaskID: "assistant-review-learning-projection",
			Title:  "复盘近期负反馈",
			Description: fmt.Sprintf(
				"近期负反馈 %d 次，高优先级信号 %d 次。",
				projection.NegativeFeedbackCount,
				projection.HighPriorityCount,
			),
			Status:        "pending",
			Priority:      "high",
			SourceSkillID: "assistant_learning",
			UpdatedAt:     now.Format(time.RFC3339),
		})
	}
	if metricID, score := selectLowestMetric(projection); metricID != "" {
		status := "in_progress"
		priority := "medium"
		if score <= 2 {
			status = "pending"
			priority = "high"
		}
		items = append(items, assistant.AssistantUserTaskView{
			TaskID: "assistant-followup-metric-" + metricID,
			Title:  "检查关键评分卡",
			Description: fmt.Sprintf(
				"指标 %s 当前最新分值 %.1f，建议继续跟踪。",
				metricID,
				score,
			),
			Status:        status,
			Priority:      priority,
			SourceSkillID: "assistant_learning",
			UpdatedAt:     now.Format(time.RFC3339),
		})
	}
	return items
}
