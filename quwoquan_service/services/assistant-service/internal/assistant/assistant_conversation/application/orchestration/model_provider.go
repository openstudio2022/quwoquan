package orchestration

import (
	"context"

	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/contextassembly"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/ports"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference_fact/domain/model"
)

type ModelRequest struct {
	TurnID                string
	TraceID               string
	SkillID               string
	PolicyID              string
	PolicyReleaseDigest   string
	PolicyCohort          string
	PolicyRolloutRevision int
	PolicyRuleID          string
	PolicyTemplateID      string
	SearchIntensity       string
	ProblemClass          string
	Prompt                string
	Stage                 string
	// ToolCatalog 是本阶段允许模型选择的工具声明。非空且 adapter 支持原生工具调用时，
	// 走 tools/tool_choice 协议；否则显式降级为结构化输出协议。
	ToolCatalog             []ports.ModelToolDefinition
	Observation             map[string]any
	UserQuestion            string
	ContextTurns            []assistant.AssistantConversationContextTurn
	ContextSummary          *assistant.AssistantConversationContextSummary
	PageContext             *assistant.AssistantContextSnapshot
	IntersectionEvidence    []assistant.AuthorizedIntersectionEvidence
	ContextAssembly         *contextassembly.AssemblyResult
	SessionPreferenceFacts  []preferencemodel.Snapshot
	LongTermPreferenceFacts []preferencemodel.Snapshot
	FeedbackContext         assistant.AssistantFeedbackContextSnapshot
	SkillCatalog            []skillpkg.Manifest
}

type ModelResponse struct {
	Text                   string
	StructuredDelta        map[string]any
	Usage                  map[string]any
	FinishReason           string
	ClientModelInteraction map[string]any
	// ToolCalls 是模型以原生协议返回的工具选择；结构化输出降级路径下为空。
	ToolCalls []ports.ModelToolCall
}

type ModelProvider interface {
	Complete(ctx context.Context, req ModelRequest) (ModelResponse, error)
}

// StreamingModelProvider 仅用于最终用户可见回答。推理、技能选择与证据处理仍走
// Complete，以保证结构化 JSON 在完整解码后才进入状态机。
type StreamingModelProvider interface {
	Stream(
		ctx context.Context,
		req ModelRequest,
		emit func(ports.ModelTextDelta) error,
	) (ModelResponse, error)
}
