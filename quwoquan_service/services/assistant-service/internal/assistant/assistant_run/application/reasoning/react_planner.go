package reasoning

import (
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Budget struct {
	MaxIterations int `json:"maxIterations"`
	MaxToolCalls  int `json:"maxToolCalls"`
}

func DefaultBudget() Budget {
	return Budget{MaxIterations: 4, MaxToolCalls: 3}
}

type PlanInput struct {
	ReasoningText   string
	StructuredDelta map[string]any
	ToolPolicy      []string
	Budget          Budget
}

type PlanStep struct {
	StepID   string         `json:"stepId"`
	Action   string         `json:"action"`
	ToolName string         `json:"toolName,omitempty"`
	Input    map[string]any `json:"input,omitempty"`
}

// AskUser 是反问请求，形状对齐契约 assistant_turn.ask_user。
type AskUser struct {
	SlotID      string   `json:"slotId,omitempty"`
	Prompt      string   `json:"prompt"`
	Required    bool     `json:"required"`
	Suggestions []string `json:"suggestions,omitempty"`
}

// Decision 是 planner 的唯一输出。动作取值由契约枚举 AssistantNextAction 决定，
// 编排层不再比较裸字符串。
type Decision struct {
	NextAction assistantgenerated.AssistantNextAction
	ActionCode assistantgenerated.PlannerActionCode
	ToolName   string
	ToolInput  map[string]any
	AskUser    AskUser
	// Rejection records a model tool decision that must be repaired before any
	// tool may execute. It is an internal orchestration fact, not a public wire
	// contract and never authorizes a fallback tool.
	Rejection *ToolDecisionRejection
	// ReasonCode 说明该决策为何偏离模型请求的动作，只用于日志与回放断言。
	ReasonCode string
}

// ToolDecisionRejection is the bounded feedback returned to the next planning
// iteration when the model omitted or selected an unavailable tool. The
// alternatives are the effective runtime/guard intersection, not a tool to be
// executed implicitly.
type ToolDecisionRejection struct {
	ReasonCode    string
	RequestedTool string
	AllowedTools  []string
	Retryable     bool
}

func (d Decision) CallsTool() bool {
	return d.Rejection == nil &&
		d.NextAction == assistantgenerated.AssistantNextActionToolCall &&
		strings.TrimSpace(d.ToolName) != ""
}

func (d Decision) Rejected() bool {
	return d.Rejection != nil
}

// RejectTool converts a requested tool call into a non-executable decision.
// The caller can feed the rejection back to the model for an explicit repair;
// choosing an alternative remains the model's responsibility.
func (d Decision) RejectTool(reasonCode string, allowedTools []string) Decision {
	reasonCode = strings.TrimSpace(reasonCode)
	d.ReasonCode = reasonCode
	d.ActionCode = assistantgenerated.PlannerActionCodeRecoverRetrieval
	d.Rejection = &ToolDecisionRejection{
		ReasonCode:    reasonCode,
		RequestedTool: strings.TrimSpace(d.ToolName),
		AllowedTools:  normalizedToolPolicy(allowedTools),
	}
	d.Rejection.Retryable = len(d.Rejection.AllowedTools) > 0
	return d
}

func (d Decision) AsksUser() bool {
	return d.NextAction == assistantgenerated.AssistantNextActionAskUser &&
		strings.TrimSpace(d.AskUser.Prompt) != ""
}

func (d Decision) Aborts() bool {
	return d.NextAction == assistantgenerated.AssistantNextActionAbort
}

// PlanSteps 是 Decision 的派生视图，供过程可观测使用；它不构成第二份决策真相源。
func (d Decision) PlanSteps() []PlanStep {
	if d.Rejected() {
		return []PlanStep{{StepID: "repair_decision", Action: "replan"}}
	}
	if d.CallsTool() {
		return []PlanStep{{
			StepID:   "tool:1",
			Action:   "tool",
			ToolName: d.ToolName,
			Input:    d.ToolInput,
		}, {
			StepID: "answer",
			Action: "answer",
		}}
	}
	if d.AsksUser() {
		return []PlanStep{{StepID: "ask_user", Action: "ask_user"}}
	}
	return []PlanStep{{StepID: "answer", Action: "answer"}}
}

type ReactPlanner struct{}

// Decide 把模型的结构化决策通道翻译成受预算与工具策略约束的执行动作。
func (ReactPlanner) Decide(input PlanInput) Decision {
	requested, parseFailure := requestedNextAction(input.StructuredDelta)
	switch requested {
	case assistantgenerated.AssistantNextActionAskUser:
		ask := askUserFrom(input.StructuredDelta)
		if strings.TrimSpace(ask.Prompt) == "" {
			// 反问必须带可展示的问题，否则退回作答，不向用户输出空反问。
			return answerDecision("ask_user_without_prompt")
		}
		return Decision{
			NextAction: assistantgenerated.AssistantNextActionAskUser,
			ActionCode: assistantgenerated.PlannerActionCodeAskClarification,
			AskUser:    ask,
		}
	case assistantgenerated.AssistantNextActionAbort:
		return Decision{
			NextAction: assistantgenerated.AssistantNextActionAbort,
			ActionCode: assistantgenerated.PlannerActionCodeFallbackWithExistingEvidence,
			ReasonCode: strings.TrimSpace(stringField(input.StructuredDelta, "reasonCode")),
		}
	case assistantgenerated.AssistantNextActionAnswer:
		return answerDecision("")
	}
	if input.Budget.MaxToolCalls <= 0 {
		return answerDecision("tool_budget_exhausted")
	}
	if len(input.ToolPolicy) == 0 {
		return answerDecision("no_allowed_tool")
	}
	toolName := strings.TrimSpace(stringField(input.StructuredDelta, "toolName"))
	toolInput := map[string]any(nil)
	if toolName != "" {
		if raw, ok := input.StructuredDelta["toolInput"].(map[string]any); ok {
			toolInput = raw
		}
	}
	if toolName == "" {
		if requested == assistantgenerated.AssistantNextActionUnknown && !parseFailure {
			return answerDecision("no_structured_tool_decision")
		}
		return Decision{
			NextAction: requested,
			ActionCode: assistantgenerated.PlannerActionCodeRecoverRetrieval,
		}.RejectTool("tool_name_required", input.ToolPolicy)
	}
	decision := Decision{
		NextAction: assistantgenerated.AssistantNextActionToolCall,
		ActionCode: assistantgenerated.PlannerActionCodeExecuteSearch,
		ToolName:   toolName,
		ToolInput:  toolInput,
	}
	switch requested {
	case assistantgenerated.AssistantNextActionReplan:
		decision.ActionCode = assistantgenerated.PlannerActionCodeExpandSearch
	case assistantgenerated.AssistantNextActionRetry:
		decision.ActionCode = assistantgenerated.PlannerActionCodeRecoverRetrieval
	case assistantgenerated.AssistantNextActionUnknown:
		if parseFailure {
			decision.ReasonCode = "unparsable_next_action"
		}
	}
	return decision
}

func answerDecision(reasonCode string) Decision {
	return Decision{
		NextAction: assistantgenerated.AssistantNextActionAnswer,
		ActionCode: assistantgenerated.PlannerActionCodeComposeAnswer,
		ReasonCode: reasonCode,
	}
}

// requestedNextAction 解析模型请求的动作。无法解析时按 unknown 处理并标记解析失败：
// 模型输出属于运行时输入，不能因为一次脏输出让整轮失败。
func requestedNextAction(delta map[string]any) (assistantgenerated.AssistantNextAction, bool) {
	raw := strings.TrimSpace(stringField(delta, "nextAction"))
	if raw == "" {
		return assistantgenerated.AssistantNextActionUnknown, false
	}
	action, err := assistantgenerated.ParseAssistantNextAction(raw)
	if err != nil {
		return assistantgenerated.AssistantNextActionUnknown, true
	}
	return action, false
}

func askUserFrom(delta map[string]any) AskUser {
	raw, ok := delta["askUser"].(map[string]any)
	if !ok {
		return AskUser{}
	}
	ask := AskUser{
		SlotID:   strings.TrimSpace(stringField(raw, "slotId")),
		Prompt:   strings.TrimSpace(stringField(raw, "prompt")),
		Required: boolField(raw, "required"),
	}
	switch suggestions := raw["suggestions"].(type) {
	case []string:
		for _, suggestion := range suggestions {
			if trimmed := strings.TrimSpace(suggestion); trimmed != "" {
				ask.Suggestions = append(ask.Suggestions, trimmed)
			}
		}
	case []any:
		for _, entry := range suggestions {
			text, ok := entry.(string)
			if !ok {
				continue
			}
			if trimmed := strings.TrimSpace(text); trimmed != "" {
				ask.Suggestions = append(ask.Suggestions, trimmed)
			}
		}
	}
	return ask
}

func normalizedToolPolicy(toolPolicy []string) []string {
	normalized := make([]string, 0, len(toolPolicy))
	seen := map[string]bool{}
	for _, candidate := range toolPolicy {
		trimmed := strings.TrimSpace(candidate)
		if trimmed != "" && !seen[trimmed] {
			normalized = append(normalized, trimmed)
			seen[trimmed] = true
		}
	}
	return normalized
}

func stringField(source map[string]any, key string) string {
	if source == nil {
		return ""
	}
	value, _ := source[key].(string)
	return value
}

func boolField(source map[string]any, key string) bool {
	if source == nil {
		return false
	}
	value, _ := source[key].(bool)
	return value
}

type ReactReflector struct{}

func (ReactReflector) ShouldReplan(observation Observation, budget Budget) bool {
	return observation.Empty && budget.MaxIterations > 1
}

type Observation struct {
	Empty   bool
	Summary string
}
