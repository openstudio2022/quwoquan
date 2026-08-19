// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#gwt-001
package main

import (
	"strings"
	"testing"
)

// 锁定「必填缺失即解码失败」与「可缺字段保留缺席」这两条已经成立的行为。
//
// 生成器内确实存在 `(json['x'] ?? ”).toString()` 这类补值表达式，但它位于
// assistantWireEmitJsonValidation 之后，对必填字段是不可达的防御分支而不是伪造成功。
// 这个区别只由 validation 是否覆盖该字段决定，一旦哪次改动让 validation 漏掉某个
// 类型，同一段补值就会立刻从死代码变成静默塌陷，且生成物看不出差别。所以把两侧
// 同时钉住：validation 必须覆盖每个必填标量，可缺字段必须解码成 null。
func TestAssistantWireRequiredScalarsFailClosedOnAbsence(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"AssistantNullabilityProbe": {
			Fields: []fieldDef{
				{Name: "title", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "retries", Type: "int", Constraints: []string{"NOT_NULL"}},
				{Name: "enabled", Type: "bool", Constraints: []string{"NOT_NULL"}},
				{Name: "payload", Type: "object", Constraints: []string{"NOT_NULL"}},
			},
		},
	}}

	generated := renderAssistantCloudApiWireDart(
		fields,
		[]string{"AssistantNullabilityProbe"},
		nil,
	)

	for _, field := range []string{"title", "retries", "enabled", "payload"} {
		absence := "if (!json.containsKey('" + field + "') || json['" + field + "'] == null"
		if !strings.Contains(generated, absence) {
			t.Fatalf(
				"required field %q lost its absence guard; any decode-time default "+
					"below it would silently fabricate a value:\n%s",
				field,
				generated,
			)
		}
	}
}

func TestAssistantWireNullableScalarsKeepAbsenceDistinctFromEmpty(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"AssistantNullabilityProbe": {
			Fields: []fieldDef{
				{Name: "traceId", Type: "string", Constraints: []string{"NULLABLE"}},
				{Name: "revision", Type: "int", Constraints: []string{"NULLABLE"}},
				{Name: "verified", Type: "bool", Constraints: []string{"NULLABLE"}},
			},
		},
	}}

	generated := renderAssistantCloudApiWireDart(
		fields,
		[]string{"AssistantNullabilityProbe"},
		nil,
	)

	for _, marker := range []string{
		"final String? traceId;",
		"final int? revision;",
		"final bool? verified;",
		"traceId: json['traceId']?.toString(),",
		"revision: (json['revision'] as num?)?.toInt(),",
		"verified: (json['verified'] as bool?),",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("nullable field lost its absent state, missing %q:\n%s", marker, generated)
		}
	}

	for _, collapsed := range []string{
		"traceId: (json['traceId'] ?? '').toString(),",
		"revision: (json['revision'] as num?)?.toInt() ?? 0,",
		"verified: json['verified'] == true,",
	} {
		if strings.Contains(generated, collapsed) {
			t.Fatalf(
				"nullable field collapsed absence into an empty/zero value via %q; "+
					"callers can no longer tell \"not provided\" from \"provided as empty\":\n%s",
				collapsed,
				generated,
			)
		}
	}
}

// rtc 管线的可空性来自 events.yaml 的 client_payload_defaults，而不是 fields.yaml
// 的 NOT_NULL / NULLABLE —— 这是第三套字段 authoring（见 spec OPEN-003）。
//
// 在它收敛之前，至少要钉死这条：**没有 default 的字段必须保留缺席**。一旦哪次改动
// 让无 default 的 String 落到 `as String? ?? ”`，端侧就再也分不清「网关没发这个键」
// 和「网关发了空串」，而 rtc 的字段大多是 sessionId / reason 这类，空串和没有的处置
// 完全不同。
func TestRtcPayloadWithoutDefaultKeepsAbsence(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"CallSession": {
			Fields: []fieldDef{
				{Name: "sessionId", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "retryCount", Type: "int", Constraints: []string{"NOT_NULL"}},
				{Name: "muted", Type: "bool", Constraints: []string{"NOT_NULL"}},
			},
		},
	}}
	events := &rtcEventsYAML{Events: []rtcEventYAML{{
		Name:          "nullability_probe",
		ClientWsType:  "nullability.probe",
		PayloadFields: []string{"sessionId", "retryCount", "muted"},
	}}}

	generated := renderRtcSignalPayloadsDart("probe.yaml", fields, events)

	for _, marker := range []string{
		"final String? sessionId;",
		"final int? retryCount;",
		"final bool? muted;",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("无 default 的 rtc 字段丢失了缺席态，缺 %q:\n%s", marker, generated)
		}
	}
	for _, collapsed := range []string{"?? ''", "?? \"\"", "?? 0,", "?? false,"} {
		if strings.Contains(generated, collapsed) {
			t.Fatalf(
				"无 default 的 rtc 字段把缺席塌陷成了零值（%q）；"+
					"缺席只能由 events.yaml 的显式 default 消除：\n%s",
				collapsed,
				generated,
			)
		}
	}
}

// 与上一条互为对照：**声明了 default 的字段必须用该 default**，且补值必须能追溯到
// events.yaml 上的那一行，而不是生成器自行发明的零值。
func TestRtcPayloadWithDefaultUsesDeclaredValue(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"CallSession": {
			Fields: []fieldDef{
				{Name: "retryCount", Type: "int", Constraints: []string{"NOT_NULL"}},
				{Name: "muted", Type: "bool", Constraints: []string{"NOT_NULL"}},
			},
		},
	}}
	events := &rtcEventsYAML{Events: []rtcEventYAML{{
		Name:                  "nullability_probe",
		ClientWsType:          "nullability.probe",
		PayloadFields:         []string{"retryCount", "muted"},
		ClientPayloadDefaults: map[string]string{"retryCount": "3", "muted": "true"},
	}}}

	generated := renderRtcSignalPayloadsDart("probe.yaml", fields, events)

	for _, marker := range []string{
		"final int retryCount;",
		"final bool muted;",
		"?? 3,",
		"?? true,",
	} {
		if !strings.Contains(generated, marker) {
			t.Fatalf("声明了 default 的 rtc 字段没有落到该 default，缺 %q:\n%s", marker, generated)
		}
	}
}
