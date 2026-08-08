package runtimeobservability

import (
	"sort"
	"strings"
)

// PrivacyClass 是 operation.privacy 声明的数据密级，按敏感度单调递增。
// 取值域与 ContractGraph 的 requestClassification / responseClassification 一一对应。
type PrivacyClass int

const (
	PrivacyClassPublic PrivacyClass = iota
	PrivacyClassInternal
	PrivacyClassSensitive
	PrivacyClassPII
	PrivacyClassSecret
)

// LogPolicy 是 operation.privacy.logPolicy 声明的日志载荷策略。
type LogPolicy int

const (
	// LogPolicyNone：载荷完全不进日志。
	LogPolicyNone LogPolicy = iota
	// LogPolicyMetadataOnly：只保留键与形状元数据，值一律不落盘。
	LogPolicyMetadataOnly
	// LogPolicyRedacted：低密级值可落盘，高密级值必须掩码。
	LogPolicyRedacted
)

// PayloadDirection 决定该用 request 还是 response 的密级。
type PayloadDirection int

const (
	PayloadRequest PayloadDirection = iota
	PayloadResponse
)

const (
	// RedactedValue 是掩码后的占位值；高密级字段的值一律折成它。
	RedactedValue = "[REDACTED]"
	// OmittedValue 是 metadata_only 下的占位值：保留键的存在性，丢弃全部内容。
	OmittedValue = "[OMITTED]"
)

func (c PrivacyClass) String() string {
	switch c {
	case PrivacyClassPublic:
		return "PUBLIC"
	case PrivacyClassInternal:
		return "INTERNAL"
	case PrivacyClassSensitive:
		return "SENSITIVE"
	case PrivacyClassPII:
		return "PII"
	case PrivacyClassSecret:
		return "SECRET"
	}
	return "UNKNOWN"
}

// OperationPrivacyPolicy 是单个 operation 的运行时脱敏策略，由 codegen 从 ContractGraph 派生。
type OperationPrivacyPolicy struct {
	OperationID            string
	Domain                 string
	Metric                 string
	RequestClassification  PrivacyClass
	ResponseClassification PrivacyClass
	LogPolicy              LogPolicy
	// TelemetryAttributes 是契约声明的埋点维度白名单；埋点只允许出现这些键。
	TelemetryAttributes []string
}

func (p OperationPrivacyPolicy) classificationFor(direction PayloadDirection) PrivacyClass {
	if direction == PayloadRequest {
		return p.RequestClassification
	}
	return p.ResponseClassification
}

// OperationPrivacyRedactor 在日志与埋点出口执行 operation.privacy 声明的脱敏策略。
//
// 查不到策略时 fail-closed：未知 operation 的载荷按 SECRET + LogPolicyNone 处理。
// 静默放行未登记的 operation 等于把「契约没覆盖到」变成「运行时泄漏」。
type OperationPrivacyRedactor struct {
	policies map[string]OperationPrivacyPolicy
}

// NewOperationPrivacyRedactor 绑定 codegen 派生的策略表。
func NewOperationPrivacyRedactor() *OperationPrivacyRedactor {
	return &OperationPrivacyRedactor{policies: generatedOperationPrivacyPolicies}
}

// newOperationPrivacyRedactorWith 只服务测试，允许注入受控策略表。
func newOperationPrivacyRedactorWith(policies map[string]OperationPrivacyPolicy) *OperationPrivacyRedactor {
	return &OperationPrivacyRedactor{policies: policies}
}

// Policy 返回 operation 的派生策略；第二个返回值为 false 表示该 operation 未登记。
func (r *OperationPrivacyRedactor) Policy(operationID string) (OperationPrivacyPolicy, bool) {
	policy, ok := r.policies[strings.TrimSpace(operationID)]
	return policy, ok
}

// OperationIDs 返回全部已登记 operation，供门禁与测试枚举。
func (r *OperationPrivacyRedactor) OperationIDs() []string {
	ids := make([]string, 0, len(r.policies))
	for id := range r.policies {
		ids = append(ids, id)
	}
	sort.Strings(ids)
	return ids
}

// RedactLogPayload 按 operation.privacy 对将要落日志的载荷脱敏。
//
// logPolicy 决定「值能否落盘」，classification 决定「哪些值必须掩码、哪些键必须整条丢弃」：
//   - LogPolicyNone：整个载荷不落盘。
//   - LogPolicyMetadataOnly：保留键，值折成 OmittedValue。
//   - LogPolicyRedacted：PUBLIC / INTERNAL 值原样落盘，SENSITIVE / PII 值掩码。
//
// SECRET 无论 logPolicy 如何都整条丢弃：掩码值本身也会暴露该字段存在。
func (r *OperationPrivacyRedactor) RedactLogPayload(
	operationID string,
	direction PayloadDirection,
	payload map[string]any,
) map[string]any {
	policy, ok := r.Policy(operationID)
	if !ok {
		return map[string]any{}
	}
	class := policy.classificationFor(direction)
	if policy.LogPolicy == LogPolicyNone || class == PrivacyClassSecret {
		return map[string]any{}
	}
	result := make(map[string]any, len(payload))
	for key, value := range payload {
		switch {
		case policy.LogPolicy == LogPolicyMetadataOnly:
			result[key] = OmittedValue
		case class >= PrivacyClassSensitive:
			result[key] = RedactedValue
		default:
			result[key] = value
		}
	}
	return result
}

// RedactTelemetryAttributes 把埋点维度收敛到契约声明的白名单。
//
// 埋点是无差别外发的高基数入口：任何没有在 telemetry.attributes 里声明的键都可能是业务载荷，
// 直接丢弃而不是掩码——掩码后的键仍会进入指标维度并制造基数。
func (r *OperationPrivacyRedactor) RedactTelemetryAttributes(
	operationID string,
	attributes map[string]string,
) map[string]string {
	policy, ok := r.Policy(operationID)
	if !ok {
		return map[string]string{}
	}
	allowed := make(map[string]bool, len(policy.TelemetryAttributes))
	for _, attribute := range policy.TelemetryAttributes {
		allowed[attribute] = true
	}
	result := make(map[string]string, len(attributes))
	for key, value := range attributes {
		if allowed[key] {
			result[key] = value
		}
	}
	return result
}
