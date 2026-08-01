package orchestration

import (
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
)

const pageContextTTL = 5 * time.Minute

type AssistantService struct {
	consents                   consentports.Reader
	consentQueries             *consentapplication.QueryFacade
	cache                      rtredis.Client
	notificationMessages       ports.NotificationAppMessageCommandWriter
	subscriptions              ports.SkillSubscriptionStore
	deliveryPolicies           ports.AssistantDeliveryPolicyReader
	creationGrounding          ports.CreationSuggestGrounding
	xiaoquSearch               XiaoquSearchReader
	intersectionInbox          ports.IntersectionInboxReader
	intersectionEvidence       ports.IntersectionEvidenceReader
	frozenPolicies             ports.FrozenPolicyResolver
	policySkillCandidates      ports.PolicySkillCandidateResolver
	learningFacts              ports.LearningFactWriter
	learningProjection         ports.LearningProjectionReader
	chatGrounding              ports.ChatGroundingClient
	agentLoop                  *AgentLoop
	sessionRuns                ports.SessionRunStore
	preferenceSnapshots        ports.PreferenceSnapshotReader
	runEvents                  AssistantRunEventStore
	runCancels                 *runCancelRegistry
	runExecutions              *runExecutionRegistry
	runCommands                *runruntime.CommandService
	intersectionReminderPolicy IntersectionReminderPolicy
	now                        func() time.Time
}

type AssistantServiceOption func(*AssistantService)

func WithAgentLoop(loop *AgentLoop) AssistantServiceOption {
	return func(s *AssistantService) { s.agentLoop = loop }
}

func WithRunCommandService(
	commands *runruntime.CommandService,
) AssistantServiceOption {
	return func(service *AssistantService) {
		service.runCommands = commands
	}
}

func (s *AssistantService) RunCommandService() *runruntime.CommandService {
	if s == nil {
		return nil
	}
	return s.runCommands
}

func WithPreferenceSnapshotReader(reader ports.PreferenceSnapshotReader) AssistantServiceOption {
	return func(s *AssistantService) { s.preferenceSnapshots = reader }
}

func WithSkillSubscriptionStore(store ports.SkillSubscriptionStore) AssistantServiceOption {
	return func(s *AssistantService) { s.subscriptions = store }
}

func WithAssistantDeliveryPolicyReader(
	reader ports.AssistantDeliveryPolicyReader,
) AssistantServiceOption {
	return func(s *AssistantService) { s.deliveryPolicies = reader }
}

func WithCreationSuggestGrounding(grounding ports.CreationSuggestGrounding) AssistantServiceOption {
	return func(s *AssistantService) { s.creationGrounding = grounding }
}

func WithIntersectionInboxReader(reader ports.IntersectionInboxReader) AssistantServiceOption {
	return func(s *AssistantService) { s.intersectionInbox = reader }
}

func WithIntersectionEvidenceReader(reader ports.IntersectionEvidenceReader) AssistantServiceOption {
	return func(s *AssistantService) { s.intersectionEvidence = reader }
}

func WithFrozenPolicyResolver(resolver ports.FrozenPolicyResolver) AssistantServiceOption {
	return func(service *AssistantService) {
		service.frozenPolicies = resolver
	}
}

func WithPolicySkillCandidateResolver(
	resolver ports.PolicySkillCandidateResolver,
) AssistantServiceOption {
	return func(service *AssistantService) {
		service.policySkillCandidates = resolver
	}
}

func WithLearningFactWriter(writer ports.LearningFactWriter) AssistantServiceOption {
	return func(service *AssistantService) {
		service.learningFacts = writer
	}
}

func WithLearningProjectionReader(
	reader ports.LearningProjectionReader,
) AssistantServiceOption {
	return func(service *AssistantService) {
		service.learningProjection = reader
	}
}

func WithIntersectionReminderPolicy(policy IntersectionReminderPolicy) AssistantServiceOption {
	return func(s *AssistantService) {
		s.intersectionReminderPolicy = normalizeIntersectionReminderPolicy(policy)
	}
}

func NewAssistantService(
	consents consentports.Reader,
	cache rtredis.Client,
	opts ...AssistantServiceOption,
) *AssistantService {
	svc := &AssistantService{
		consents:                   consents,
		cache:                      cache,
		runCancels:                 newRunCancelRegistry(),
		runExecutions:              newRunExecutionRegistry(),
		intersectionReminderPolicy: defaultIntersectionReminderPolicy(),
		now: func() time.Time {
			return time.Now().UTC()
		},
	}
	for _, opt := range opts {
		opt(svc)
	}
	svc.consentQueries = consentapplication.NewQueryFacade(consents)
	if svc.agentLoop == nil {
		svc.agentLoop = NewAgentLoop(nil, ReactRuntime{}, svc.now)
	}
	return svc
}

func buildSuggestedActions(
	pageType assistantgenerated.AssistantPageContextType,
	objectID string,
) ([]assistant.SuggestedAction, error) {
	objectID = strings.TrimSpace(objectID)
	pageTypeWire := pageType.WireName()
	base := []assistant.SuggestedAction{
		{
			ActionID: "assistant.ask_followup",
			Type:     "open_assistant",
			Label:    "继续追问小趣",
			Icon:     "sparkles",
			Payload:  suggestedActionPayload(pageTypeWire, objectID),
		},
	}
	switch pageType {
	case assistantgenerated.AssistantPageContextTypeDiscovery:
		return append(base,
			suggestedAction(
				"assistant.find_similar_content",
				"find_similar",
				"发现相似内容",
				"travel_explore",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.explain_discovery_feed",
				"explain_feed",
				"解释当前推荐",
				"help",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeCircles:
		return append(base,
			suggestedAction(
				"assistant.summarize_circle_discussion",
				"summarize_discussion",
				"总结圈内讨论",
				"forum",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.find_related_circles",
				"find_circles",
				"查找相关圈子",
				"groups",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeArticle:
		return append(base,
			suggestedAction(
				"assistant.summarize_article",
				"summarize",
				"总结这篇内容",
				"article",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.extract_article_entities",
				"extract_entities",
				"提取关键实体",
				"label",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeProfile:
		return append(base,
			suggestedAction(
				"assistant.explain_profile",
				"explain_profile",
				"了解此主页",
				"account_circle",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.find_profile_related_content",
				"find_related",
				"查找相关内容",
				"travel_explore",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeChat:
		return append(base,
			suggestedAction(
				"assistant.summarize_conversation",
				"summarize_conversation",
				"总结当前对话",
				"forum",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.draft_chat_reply",
				"draft_reply",
				"帮我拟一条回复",
				"edit",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeCreate:
		return append(base,
			suggestedAction(
				"assistant.improve_creation_draft",
				"improve_draft",
				"优化创作草稿",
				"edit_note",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.plan_creation_publish",
				"plan_publish",
				"规划发布步骤",
				"checklist",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeSearch:
		return append(base,
			suggestedAction(
				"assistant.refine_search_query",
				"refine_query",
				"优化搜索词",
				"manage_search",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.compare_search_results",
				"compare_results",
				"对比搜索结果",
				"compare",
				pageTypeWire,
				objectID,
			),
		), nil
	case assistantgenerated.AssistantPageContextTypeHome:
		return append(base,
			suggestedAction(
				"assistant.suggest_next_step",
				"suggest_next_step",
				"推荐下一步操作",
				"arrow_forward",
				pageTypeWire,
				objectID,
			),
			suggestedAction(
				"assistant.explain_home",
				"explain_page",
				"解释当前页面",
				"help",
				pageTypeWire,
				objectID,
			),
		), nil
	default:
		return nil, fmt.Errorf(
			"unsupported suggested-actions page type %q",
			pageTypeWire,
		)
	}
}

func suggestedAction(
	actionID string,
	actionType string,
	label string,
	icon string,
	pageType string,
	objectID string,
) assistant.SuggestedAction {
	return assistant.SuggestedAction{
		ActionID: actionID,
		Type:     actionType,
		Label:    label,
		Icon:     icon,
		Payload:  suggestedActionPayload(pageType, objectID),
	}
}

func suggestedActionPayload(
	pageType string,
	objectID string,
) map[string]any {
	payload := map[string]any{"pageType": pageType}
	if objectID != "" {
		payload["objectId"] = objectID
	}
	return payload
}

func encodeSuggestedActionCache(items []assistant.SuggestedAction) string {
	encoded, err := json.Marshal(items)
	if err != nil {
		return ""
	}
	return string(encoded)
}

func parseSuggestedActionCache(raw string) []assistant.SuggestedAction {
	var items []assistant.SuggestedAction
	if err := json.Unmarshal([]byte(strings.TrimSpace(raw)), &items); err != nil {
		return nil
	}
	return items
}

func filterTasks(items []assistant.AssistantUserTaskView, limit int, status string) []assistant.AssistantUserTaskView {
	filtered := make([]assistant.AssistantUserTaskView, 0, len(items))
	status = strings.TrimSpace(status)
	for _, item := range items {
		if status != "" && item.Status != status {
			continue
		}
		filtered = append(filtered, item)
	}
	if len(filtered) > limit {
		filtered = filtered[:limit]
	}
	return filtered
}

func dedupeSuggestedActions(items []assistant.SuggestedAction) []assistant.SuggestedAction {
	seen := map[string]struct{}{}
	out := make([]assistant.SuggestedAction, 0, len(items))
	for _, item := range items {
		key := strings.TrimSpace(item.ActionID)
		if key == "" {
			key = strings.TrimSpace(item.Type) + "|" + strings.TrimSpace(item.Label)
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, item)
	}
	return out
}

func dedupeTasks(items []assistant.AssistantUserTaskView) []assistant.AssistantUserTaskView {
	seen := map[string]struct{}{}
	out := make([]assistant.AssistantUserTaskView, 0, len(items))
	for _, item := range items {
		key := strings.TrimSpace(item.TaskID)
		if key == "" {
			key = strings.TrimSpace(item.Title)
		}
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		out = append(out, item)
	}
	return out
}

func selectLowestMetric(
	profile *learningmodel.LearningProjection,
) (string, float64) {
	if profile == nil || len(profile.LatestMetricScores) == 0 {
		return "", 0
	}
	keys := make([]string, 0, len(profile.LatestMetricScores))
	for key := range profile.LatestMetricScores {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	selected := keys[0]
	lowest := profile.LatestMetricScores[selected]
	for _, key := range keys[1:] {
		if value := profile.LatestMetricScores[key]; value < lowest {
			selected = key
			lowest = value
		}
	}
	return selected, lowest
}

func fallbackUser(userID string) string {
	if strings.TrimSpace(userID) == "" {
		return "anonymous"
	}
	return userID
}

func IsNotFound(err error) bool {
	return errors.Is(err, rtredis.ErrKeyNotFound)
}
