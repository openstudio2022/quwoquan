package tool

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
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
	ToolName             string             `json:"toolName"`
	DisplayName          string             `json:"displayName,omitempty"`
	Description          string             `json:"description,omitempty"`
	Namespace            string             `json:"namespace"`
	Placement            string             `json:"placement"`
	InputSchema          map[string]any     `json:"inputSchema"`
	OutputSchema         map[string]any     `json:"outputSchema"`
	RequiresConfirmation bool               `json:"requiresConfirmation"`
	Idempotency          string             `json:"idempotency"`
	Sensitivity          string             `json:"sensitivity"`
	EnvironmentScopes    []string           `json:"environmentScopes"`
	ServerInjectedInputs []string           `json:"serverInjectedInputs"`
	ReadOnly             bool               `json:"readOnly"`
	Capability           CapabilityPolicy   `json:"capability"`
	Confirmation         ConfirmationPolicy `json:"confirmation"`
	Resilience           ResiliencePolicy   `json:"resilience"`
	Recovery             RecoveryPolicy     `json:"recovery"`
}

// CapabilityPolicy 是 Tool Fabric 在每个安全边界重新求交的厂商无关能力合同。
// connectionRef、Consent 与 surface 的当前值由运行时读取，不冻结进工具目录。
type CapabilityPolicy struct {
	CapabilityKey        string   `json:"capabilityKey"`
	ConnectorRequirement string   `json:"connectorRequirement"`
	ConsentScopes        []string `json:"consentScopes"`
	AllowedSurfaceKinds  []string `json:"allowedSurfaceKinds"`
	RecheckAtExecution   bool     `json:"recheckAtExecution"`
}

type ConfirmationPolicy struct {
	TemplateRef       string                     `json:"templateRef"`
	Title             string                     `json:"title"`
	Description       string                     `json:"description"`
	CompletionSummary string                     `json:"completionSummary"`
	DisplayFields     []ConfirmationDisplayField `json:"displayFields"`
}

type ConfirmationDisplayField struct {
	InputKey string `json:"inputKey"`
	Label    string `json:"label"`
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
	canonicalRequired := make([]any, 0, len(names))
	for _, name := range names {
		canonicalRequired = append(canonicalRequired, name)
	}
	return map[string]any{
		"type":                 "object",
		"additionalProperties": false,
		"properties":           properties,
		// jsonschema.Compiler consumes canonical JSON values. A Go []string is
		// not a JSON array to the metaschema validator even though encoding/json
		// would later serialize it as one, so keep the in-memory schema canonical
		// at construction time as well as after catalog decoding.
		"required": canonicalRequired,
	}
}

// StringProperty 是 JSON Schema 字符串属性的最小构造，避免各处手写 map 字面量。
func StringProperty(description string) map[string]any {
	return map[string]any{"type": "string", "description": description}
}

func DefaultMetadata(toolName string) Metadata {
	return Metadata{
		ToolName:          toolName,
		DisplayName:       toolName,
		Namespace:         "custom",
		Placement:         PlacementCloud,
		Idempotency:       "none",
		Sensitivity:       "internal",
		EnvironmentScopes: []string{"alpha", "beta", "gamma", "prod"},
		ReadOnly:          true,
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

// CanonicalMetadata 只解码由 canonical catalog 生成的不可变 JSON。每次返回新对象，
// 防止调用方修改 schema map 后污染后续模型声明或运行时校验。
func CanonicalMetadata() []Metadata {
	var catalog []Metadata
	if err := json.Unmarshal(
		[]byte(assistantgenerated.AssistantToolCatalogJSON),
		&catalog,
	); err != nil {
		panic(fmt.Sprintf("decode generated assistant tool catalog: %v", err))
	}
	return catalog
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
	return mustCanonicalMetadata("web_search")
}

func AppSearchMetadata() Metadata {
	return mustCanonicalMetadata("app_search")
}

func CalendarCreateReminderMetadata() Metadata {
	return mustCanonicalMetadata("calendar_create_reminder")
}

func WebOpenMetadata() Metadata {
	return mustCanonicalMetadata("web_open")
}

func WebFindMetadata() Metadata {
	return mustCanonicalMetadata("web_find")
}

func mustCanonicalMetadata(toolName string) Metadata {
	for _, metadata := range CanonicalMetadata() {
		if metadata.ToolName == toolName {
			return metadata
		}
	}
	panic(fmt.Sprintf("generated assistant tool catalog has no %q", toolName))
}
