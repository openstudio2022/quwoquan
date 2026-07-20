package application

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.opentelemetry.io/otel/attribute"

	rterr "quwoquan_service/runtime/errors"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

func (s *AssistantService) GetPolicy(ctx context.Context, userID string) (_ assistant.AssistantPolicyView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetPolicy",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	now := s.now()
	return assistant.AssistantPolicyView{
		Version: "assistant_policy_v1",
		Values: map[string]any{
			"learningSyncEnabled":     true,
			"suggestedActionsEnabled": true,
			"pageContextTtlSeconds":   int(pageContextTTL / time.Second),
			"searchFallbackMode":      "summary_with_citations",
			"defaultSearchIntensity":  "balanced",
		},
		UpdatedAt: &now,
	}, nil
}

func (s *AssistantService) ReportPageContext(ctx context.Context, userID string, input assistant.PageContextInput) (_ assistant.PageContextAck, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ReportPageContext",
		attribute.String("user.id", userID),
		attribute.String("page.type", input.PageType))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(userID) == "" {
		return assistant.PageContextAck{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	if strings.TrimSpace(input.PageType) == "" {
		return assistant.PageContextAck{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "pageType 不能为空", "missing pageType")
	}
	contextKey := fmt.Sprintf("page_ctx:%s", userID)
	now := s.now()
	expiresAt := now.Add(pageContextTTL)
	if s.cache != nil {
		_ = s.cache.HSet(ctx, contextKey, "pageType", input.PageType)
		_ = s.cache.HSet(ctx, contextKey, "userAction", input.UserAction)
		_ = s.cache.HSet(ctx, contextKey, "subAccountId", input.SubAccountID)
		_ = s.cache.HSet(ctx, contextKey, "personaContextVersion", input.PersonaContextVersion)
		if len(input.UserActions) > 0 {
			_ = s.cache.HSet(ctx, contextKey, "userActions", strings.Join(input.UserActions, ","))
		}
		if len(input.BusinessObjects) > 0 {
			objectIDs := make([]string, 0, len(input.BusinessObjects))
			for _, item := range input.BusinessObjects {
				if objectID := strings.TrimSpace(fmt.Sprint(item["objectId"])); objectID != "" && objectID != "<nil>" {
					objectIDs = append(objectIDs, objectID)
				}
			}
			if len(objectIDs) > 0 {
				_ = s.cache.HSet(ctx, contextKey, "objectIds", strings.Join(objectIDs, ","))
			}
		}
		_ = s.cache.HSet(ctx, contextKey, "updatedAt", now.Format(time.RFC3339))
		_ = s.cache.Expire(ctx, contextKey, pageContextTTL)
	}
	return assistant.PageContextAck{Accepted: true, ContextKey: contextKey, ExpiresAt: &expiresAt}, nil
}

func (s *AssistantService) GetSuggestedActions(ctx context.Context, userID string, pageType string, objectID string) (_ assistant.SuggestedActionListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetSuggestedActions",
		attribute.String("user.id", userID),
		attribute.String("page.type", pageType))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(pageType) == "" {
		return assistant.SuggestedActionListView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "pageType 不能为空", "missing pageType")
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
	items := buildSuggestedActions(pageType, objectID)
	if s.profiles != nil && strings.TrimSpace(userID) != "" {
		if profile, err := s.profiles.GetLearningProfile(ctx, userID); err == nil && profile != nil {
			if profile.NegativeFeedbackCount > 0 || profile.HighPriorityCount > 0 {
				items = append(items, assistant.SuggestedAction{ActionID: "assistant.review_recent_feedback", Type: "review_feedback", Label: "复盘近期反馈", Icon: "thumb_down", Payload: map[string]any{"scope": "learning_profile", "userId": userID}})
			}
			if metricID, metricScore := selectLowestMetric(profile); metricID != "" && metricScore <= 3 {
				items = append(items, assistant.SuggestedAction{ActionID: "assistant.inspect_metric", Type: "inspect_metric", Label: "检查低分指标", Icon: "monitor_heart", Payload: map[string]any{"metricId": metricID, "score": metricScore}})
			}
		}
	}
	if s.cache != nil && len(items) > 0 {
		_ = s.cache.Set(ctx, cacheKey, encodeSuggestedActionCache(items), pageContextTTL)
	}
	return assistant.SuggestedActionListView{Items: dedupeSuggestedActions(items)}, nil
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
	if s.profiles == nil || strings.TrimSpace(userID) == "" {
		return view, nil
	}
	profile, profileErr := s.profiles.GetLearningProfile(ctx, userID)
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
		return assistant.AssistantSearchResultView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "query 不能为空", "missing userQuery")
	}
	intensity := strings.TrimSpace(req.SearchIntensity)
	if intensity == "" {
		intensity = "balanced"
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
		citations = append(citations, assistant.AssistantSearchCitationView{
			CitationID:    citation.CitationID,
			ObjectType:    target,
			ObjectID:      citation.ObjectID,
			Title:         citation.Title,
			Snippet:       citation.Snippet,
			URL:           citation.URL,
			DeepLink:      citation.DeepLink,
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
		SearchIntensity: intensity,
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
	if s.profiles != nil && strings.TrimSpace(userID) != "" {
		projected, err := s.profiles.BuildTaskItems(ctx, userID, now)
		if err != nil {
			slog.WarnContext(ctx, "assistant task projection read failed; returning projected-only list",
				slog.String("userId", userID), slog.String("error", err.Error()))
		} else {
			items = append(items, projected...)
		}
	}
	// 只返回学习画像投影出的真实待办；无数据即诚实空态，不合成演示任务。
	return assistant.AssistantUserTaskListView{Items: filterTasks(dedupeTasks(items), limit, status)}, nil
}

func (s *AssistantService) GetLearningOpsSummary(ctx context.Context, userID string) (_ assistant.AssistantLearningOpsSummaryView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.GetLearningOpsSummary",
		attribute.String("user.id", userID))
	defer func() { rtobs.EndSpan(span, err) }()

	if strings.TrimSpace(userID) == "" {
		return assistant.AssistantLearningOpsSummaryView{}, rterr.NewInvalidArgument(rterr.ModuleAssistant, "userId 不能为空", "missing userId")
	}
	var profile *assistant.AssistantLearningProfile
	if s.profiles != nil {
		loaded, err := s.profiles.GetLearningProfile(ctx, userID)
		if err != nil {
			return assistant.AssistantLearningOpsSummaryView{}, err
		}
		profile = loaded
	}
	if profile == nil {
		profile = &assistant.AssistantLearningProfile{UserID: userID}
		if s.events != nil {
			if items, err := s.events.ListLatestInteractionEvents(ctx, userID, 1); err == nil && len(items) > 0 {
				profile.LastEventID = items[0].EventID
				profile.LastRunID = items[0].RunID
				profile.LastPageType = items[0].PageType
				profile.LastFeedbackType = items[0].FeedbackType
				profile.LastFeedbackScore = items[0].FeedbackScore
				profile.LastFeedbackAt = items[0].CreatedAt
			}
			if scores, err := s.events.ListLatestScorecards(ctx, userID, 16); err == nil {
				profile.MetricSampleCounts = map[string]int64{}
				profile.MetricScoreSums = map[string]float64{}
				profile.LatestMetricScores = map[string]float64{}
				for _, score := range scores {
					profile.MetricSampleCounts[score.MetricID]++
					profile.MetricScoreSums[score.MetricID] += score.ScoreValue
					if _, ok := profile.LatestMetricScores[score.MetricID]; !ok {
						profile.LatestMetricScores[score.MetricID] = score.ScoreValue
					}
					if profile.LastMetricID == "" {
						profile.LastMetricID = score.MetricID
						profile.LastMetricScore = score.ScoreValue
					}
				}
			}
		}
	}
	metricAverages := map[string]float64{}
	for metricID, sampleCount := range profile.MetricSampleCounts {
		if sampleCount <= 0 {
			continue
		}
		metricAverages[metricID] = profile.MetricScoreSums[metricID] / float64(sampleCount)
	}
	summary := assistant.AssistantLearningOpsSummaryView{
		UserID:                profile.UserID,
		TotalFeedbackCount:    profile.TotalFeedbackCount,
		PositiveFeedbackCount: profile.PositiveFeedbackCount,
		NegativeFeedbackCount: profile.NegativeFeedbackCount,
		TextFeedbackCount:     profile.TextFeedbackCount,
		HighPriorityCount:     profile.HighPriorityCount,
		MediumPriorityCount:   profile.MediumPriorityCount,
		LastFeedbackType:      profile.LastFeedbackType,
		LastFeedbackScore:     profile.LastFeedbackScore,
		LastMetricID:          profile.LastMetricID,
		LastMetricScore:       profile.LastMetricScore,
		TopReasonCodes:        topReasonCodes(profile.ReasonCodeCounts, 5),
		MetricAverages:        metricAverages,
		LatestMetricScores:    cloneMetricScores(profile.LatestMetricScores),
	}
	if !profile.LastFeedbackAt.IsZero() {
		summary.LastFeedbackAt = profile.LastFeedbackAt.Format(time.RFC3339)
	}
	if !profile.UpdatedAt.IsZero() {
		summary.UpdatedAt = profile.UpdatedAt.Format(time.RFC3339)
	}
	return summary, nil
}

func (s *AssistantService) ListSkills(ctx context.Context, userID string, limit int) (_ assistant.AssistantSkillCatalogListView, err error) {
	ctx, span := rtobs.StartBusinessSpan(ctx, "assistant.ListSkills",
		attribute.String("user.id", userID),
		attribute.Int("list.limit", limit))
	defer func() { rtobs.EndSpan(span, err) }()

	items, err := assistantDomainSkillCatalogViews()
	if err != nil {
		return assistant.AssistantSkillCatalogListView{}, err
	}
	items = append([]assistant.AssistantSkillCatalogItemView{}, items...)
	items = append(items, []assistant.AssistantSkillCatalogItemView{
		{SkillID: SkillDailyAssistant, DisplayName: "每日助手", Description: "管理待办、日历、会议、作息和学习计划。", Category: "life", RequiresConsent: false, IconHint: "checkmark"},
		{SkillID: SkillNewsBriefing, DisplayName: "新闻简报", Description: "按关注话题定时生成新闻摘要。", Category: "content", RequiresConsent: false, IconHint: "news"},
		{SkillID: SkillStockSentinel, DisplayName: "股票哨兵", Description: "跟踪关注股票的重大消息面和行情变化。", Category: "finance", RequiresConsent: false, IconHint: "chart"},
		{SkillID: SkillTravelJourneyManager, DisplayName: "出行旅程管家", Description: "结合天气、路况和景点拥堵提醒行程风险。", Category: "travel", RequiresConsent: false, IconHint: "airplane"},
		{SkillID: SkillPersonalContentAccess, DisplayName: "个人内容访问", Description: "允许助手在授权后读取用户个人内容用于回答与建议。", Category: "permission", RequiresConsent: true, IconHint: "lock_open"},
		{SkillID: "assistant_learning", DisplayName: "学习反馈闭环", Description: "基于交互事件与评分卡形成在线学习与运营回看。", Category: "analytics", RequiresConsent: false, IconHint: "school"},
		{SkillID: "assistant_navigation", DisplayName: "页面建议动作", Description: "根据当前 page context 返回可执行的建议动作。", Category: "navigation", RequiresConsent: false, IconHint: "bolt"},
	}...)
	if strings.TrimSpace(userID) != "" && s.consents != nil {
		consents, err := s.consents.ListActiveConsents(ctx, userID)
		if err == nil {
			granted := map[string]assistant.SkillConsent{}
			for _, consent := range consents {
				granted[consent.SkillID] = consent
			}
			for i := range items {
				if consent, ok := granted[items[i].SkillID]; ok {
					items[i].Description = items[i].Description + "（已授权：" + consent.GrantedScope + "）"
				}
			}
		}
	}
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	return assistant.AssistantSkillCatalogListView{Items: items[:limit]}, nil
}
