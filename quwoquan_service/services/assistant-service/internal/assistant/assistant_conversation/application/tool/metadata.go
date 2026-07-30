package tool

import (
	"sort"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
)

const (
	PlacementCloud         = "cloud"
	PlacementDeviceContext = "device_context"
	PlacementDeviceAction  = "device_action"
	PlacementHybrid        = "hybrid"
)

// Metadata 与 contracts/_shared/assistant_tool_metadata 同形。输入输出约束只以 JSON
// Schema 表达一次，模型工具声明与运行时校验都读同一份，避免第二套必填键清单。
type Metadata struct {
	ToolName             string           `json:"toolName"`
	DisplayName          string           `json:"displayName,omitempty"`
	Description          string           `json:"description,omitempty"`
	Placement            string           `json:"placement"`
	InputSchema          map[string]any   `json:"inputSchema"`
	OutputSchema         map[string]any   `json:"outputSchema"`
	RequiresConfirmation bool             `json:"requiresConfirmation"`
	Resilience           ResiliencePolicy `json:"resilience"`
	Recovery             RecoveryPolicy   `json:"recovery"`
}

type ResiliencePolicy struct {
	TimeoutMs           int `json:"timeoutMs"`
	MaxAttempts         int `json:"maxAttempts"`
	RetryBackoffMs      int `json:"retryBackoffMs"`
	LoopDetectionWindow int `json:"loopDetectionWindow"`
}

type RecoveryPolicy struct {
	Action             string `json:"action"`
	DisruptionLevel    string `json:"disruptionLevel"`
	UserVisibleSummary string `json:"userVisibleSummary,omitempty"`
}

// ResolvedAction 把空值补齐为 assistant_tool_metadata 的契约默认值，未知取值一律收敛到
// fail_turn，避免脏元数据让失败被静默吞掉。
func (p RecoveryPolicy) ResolvedAction() assistantgenerated.ToolRecoveryAction {
	action, err := assistantgenerated.ParseToolRecoveryAction(
		strings.TrimSpace(p.Action),
	)
	if err != nil || action == assistantgenerated.ToolRecoveryActionUnknown {
		return assistantgenerated.ToolRecoveryActionFailTurn
	}
	return action
}

// ResolvedDisruptionLevel 同样按契约默认值补齐为 partial。
func (p RecoveryPolicy) ResolvedDisruptionLevel() assistantgenerated.ToolDisruptionLevel {
	level, err := assistantgenerated.ParseToolDisruptionLevel(
		strings.TrimSpace(p.DisruptionLevel),
	)
	if err != nil || level == assistantgenerated.ToolDisruptionLevelUnknown {
		return assistantgenerated.ToolDisruptionLevelPartial
	}
	return level
}

// RequiredInputKeys 从 InputSchema 的 required 派生，运行时校验与模型声明因此不会漂移。
func (m Metadata) RequiredInputKeys() []string {
	return schemaRequiredKeys(m.InputSchema)
}

// RequiredOutputKeys 从 OutputSchema 的 required 派生。
func (m Metadata) RequiredOutputKeys() []string {
	return schemaRequiredKeys(m.OutputSchema)
}

func schemaRequiredKeys(schema map[string]any) []string {
	if schema == nil {
		return nil
	}
	switch required := schema["required"].(type) {
	case []string:
		return required
	case []any:
		keys := make([]string, 0, len(required))
		for _, item := range required {
			if key, ok := item.(string); ok && key != "" {
				keys = append(keys, key)
			}
		}
		return keys
	default:
		return nil
	}
}

// ObjectSchema 构造一个封闭的 JSON Schema object，properties 顺序稳定以便回放比对。
func ObjectSchema(properties map[string]any, required ...string) map[string]any {
	if properties == nil {
		properties = map[string]any{}
	}
	names := make([]string, 0, len(required))
	names = append(names, required...)
	sort.Strings(names)
	return map[string]any{
		"type":       "object",
		"properties": properties,
		"required":   names,
	}
}

// StringProperty 是 JSON Schema 字符串属性的最小构造，避免各处手写 map 字面量。
func StringProperty(description string) map[string]any {
	return map[string]any{"type": "string", "description": description}
}

func DefaultMetadata(toolName string) Metadata {
	return Metadata{
		ToolName:    toolName,
		DisplayName: toolName,
		Placement:   PlacementCloud,
		InputSchema: ObjectSchema(map[string]any{
			"query": StringProperty("检索主查询词。"),
		}, "query"),
		OutputSchema: ObjectSchema(map[string]any{
			"summary": StringProperty("工具结果摘要。"),
		}, "summary"),
		RequiresConfirmation: false,
		Resilience: ResiliencePolicy{
			TimeoutMs:           5000,
			MaxAttempts:         1,
			RetryBackoffMs:      0,
			LoopDetectionWindow: 3,
		},
		Recovery: RecoveryPolicy{
			Action:          "fail_turn",
			DisruptionLevel: "partial",
		},
	}
}

// CanonicalMetadata 是本服务可装配工具的唯一目录。装配根按它注册 handler，技能
// manifest 与 policy artifact 的 allowedTools 也只能引用其中的工具名，避免出现声明了
// 却永远执行失败的工具。
func CanonicalMetadata() []Metadata {
	return []Metadata{
		AppSearchMetadata(),
		WebSearchMetadata(),
	}
}

// CanonicalToolNames 返回目录内工具名，按字典序稳定输出。
func CanonicalToolNames() []string {
	catalog := CanonicalMetadata()
	names := make([]string, 0, len(catalog))
	for _, meta := range catalog {
		names = append(names, meta.ToolName)
	}
	sort.Strings(names)
	return names
}

func WebSearchMetadata() Metadata {
	meta := DefaultMetadata("web_search")
	meta.DisplayName = "网络搜索"
	meta.Description = "检索公开网络信息并返回可核验引用；也用于天气与行情等实时公共事实。"
	meta.InputSchema = ObjectSchema(map[string]any{
		"query": StringProperty("检索主查询词，使用可直接搜索的短语。"),
		"searchQueries": map[string]any{
			"type":        "array",
			"description": "多维度问题按维度拆分的结构化检索词。",
			"items": ObjectSchema(map[string]any{
				"dimension": StringProperty("该检索词覆盖的维度，例如 weather、traffic、ticket。"),
				"query":     StringProperty("该维度的检索词。"),
			}, "dimension", "query"),
		},
		"location":           StringProperty("问题涉及的地点原文写法。"),
		"locationSearchName": StringProperty("适合地理检索的拉丁写法，例如 Hangzhou。"),
		"symbol":             StringProperty("单个证券交易代码。"),
		"symbols": map[string]any{
			"type":        "array",
			"description": "多个证券交易代码。",
			"items":       map[string]any{"type": "string"},
		},
	}, "query")
	meta.OutputSchema = ObjectSchema(map[string]any{
		"summary":    StringProperty("检索结果摘要。"),
		"references": map[string]any{"type": "array", "description": "可核验引用条目。"},
	}, "summary", "references")
	return meta
}

func AppSearchMetadata() Metadata {
	meta := DefaultMetadata("app_search")
	meta.DisplayName = "应用信息检索"
	meta.Description = "通过 search-service 检索趣我圈站内公开对象（用户、圈子、内容、地点）并返回可核验引用。"
	meta.InputSchema = ObjectSchema(map[string]any{
		"query": StringProperty("站内检索词，可以是用户名、圈子名、地点名或内容关键词。"),
	}, "query")
	meta.OutputSchema = ObjectSchema(map[string]any{
		"provider":   StringProperty("检索提供方标识。"),
		"summary":    StringProperty("检索结果摘要。"),
		"results":    map[string]any{"type": "array", "description": "站内对象命中列表。"},
		"citations":  map[string]any{"type": "array", "description": "站内可核验引用。"},
		"provenance": map[string]any{"type": "object", "description": "检索来源与回查证据。"},
	}, "provider", "summary", "results", "citations", "provenance")
	return meta
}
