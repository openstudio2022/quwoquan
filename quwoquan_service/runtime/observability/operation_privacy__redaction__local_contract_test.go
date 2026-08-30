package runtimeobservability

import (
	"strings"
	"testing"
)

// 契约事实：operation.privacy 的每个取值组合都必须在日志与埋点出口产生可观测的脱敏行为。
// 这些用例直接消费 codegen 派生表，policy 与契约漂移会当场失败。

func TestOperationPrivacySecretPayloadNeverReachesLog(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	checked := 0
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		for _, direction := range []PayloadDirection{PayloadRequest, PayloadResponse} {
			if policy.classificationFor(direction) != PrivacyClassSecret {
				continue
			}
			checked++
			out := redactor.RedactLogPayload(operationID, direction, map[string]any{
				"access_token": "eyJhbGciOi.very.secret",
				"refresh":      "rt_live_9f2",
			})
			if len(out) != 0 {
				t.Fatalf("%s(%v): SECRET 载荷必须整体不落日志，实际得到 %v", operationID, direction, out)
			}
		}
	}
	if checked == 0 {
		t.Fatal("ContractGraph 中没有 SECRET 密级 operation，用例失去判定对象")
	}
	t.Logf("SECRET 方向数=%d", checked)
}

func TestOperationPrivacyHighSensitiveValuesAreMaskedInLog(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	secret := "13900000000"
	masked, kept := 0, 0
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		if policy.LogPolicy != LogPolicyRedacted {
			continue
		}
		for _, direction := range []PayloadDirection{PayloadRequest, PayloadResponse} {
			class := policy.classificationFor(direction)
			if class == PrivacyClassSecret {
				continue
			}
			out := redactor.RedactLogPayload(operationID, direction, map[string]any{"phone": secret})
			value, present := out["phone"]
			if !present {
				t.Fatalf("%s(%v): redacted 策略下键必须保留", operationID, direction)
			}
			if class >= PrivacyClassSensitive {
				if value != RedactedValue {
					t.Fatalf(
						"%s(%v): %s 值必须掩码，实际 %v", operationID, direction, class, value,
					)
				}
				masked++
				continue
			}
			if value != secret {
				t.Fatalf("%s(%v): %s 值不应被掩码，实际 %v", operationID, direction, class, value)
			}
			kept++
		}
	}
	if masked == 0 || kept == 0 {
		t.Fatalf("判定对象不足：masked=%d kept=%d", masked, kept)
	}
	t.Logf("redacted 策略下 掩码=%d 保留=%d", masked, kept)
}

func TestOperationPrivacyMetadataOnlyDropsEveryValue(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	checked := 0
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		if policy.LogPolicy != LogPolicyMetadataOnly {
			continue
		}
		if policy.RequestClassification == PrivacyClassSecret {
			continue
		}
		checked++
		out := redactor.RedactLogPayload(operationID, PayloadRequest, map[string]any{
			"id_card": "310101199001011234",
			"note":    "free text",
		})
		if len(out) != 2 {
			t.Fatalf("%s: metadata_only 必须保留键的存在性，实际 %v", operationID, out)
		}
		for key, value := range out {
			if value != OmittedValue {
				t.Fatalf("%s: metadata_only 下 %s 的值必须丢弃，实际 %v", operationID, key, value)
			}
		}
	}
	if checked == 0 {
		t.Fatal("ContractGraph 中没有 metadata_only operation，用例失去判定对象")
	}
	t.Logf("metadata_only operation 数=%d", checked)
}

func TestOperationPrivacyLogPolicyNoneDropsPayload(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	checked := 0
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		if policy.LogPolicy != LogPolicyNone {
			continue
		}
		checked++
		out := redactor.RedactLogPayload(operationID, PayloadResponse, map[string]any{"any": "value"})
		if len(out) != 0 {
			t.Fatalf("%s: logPolicy=none 必须丢弃全部载荷，实际 %v", operationID, out)
		}
	}
	if checked == 0 {
		t.Fatal("ContractGraph 中没有 logPolicy=none operation，用例失去判定对象")
	}
	t.Logf("logPolicy=none operation 数=%d", checked)
}

func TestOperationPrivacyTelemetryDropsUndeclaredAttributes(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	checked := 0
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		if len(policy.TelemetryAttributes) == 0 {
			continue
		}
		checked++
		attributes := map[string]string{
			// 契约外的高敏维度：即便调用方误传，也不允许进入指标维度。
			"phone":         "13900000000",
			"id_card":       "310101199001011234",
			"access_token":  "eyJhbGciOi",
			"user_free_txt": "任意用户输入",
		}
		for _, declared := range policy.TelemetryAttributes {
			attributes[declared] = "ok"
		}
		out := redactor.RedactTelemetryAttributes(operationID, attributes)
		if len(out) != len(policy.TelemetryAttributes) {
			t.Fatalf(
				"%s: 埋点维度必须收敛到契约白名单 %v，实际 %v",
				operationID, policy.TelemetryAttributes, out,
			)
		}
		for _, leaked := range []string{"phone", "id_card", "access_token", "user_free_txt"} {
			if _, present := out[leaked]; present {
				t.Fatalf("%s: 未声明维度 %s 泄漏进埋点", operationID, leaked)
			}
		}
	}
	if checked == 0 {
		t.Fatal("ContractGraph 中没有声明 telemetry.attributes 的 operation")
	}
	t.Logf("带 telemetry.attributes 的 operation 数=%d", checked)
}

func TestOperationPrivacyUnknownOperationFailsClosed(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	const unknown = "nonexistent.object.Operation"
	if _, ok := redactor.Policy(unknown); ok {
		t.Fatalf("%s 不应存在于派生表中", unknown)
	}
	if out := redactor.RedactLogPayload(unknown, PayloadRequest, map[string]any{"phone": "139"}); len(out) != 0 {
		t.Fatalf("未登记 operation 必须 fail-closed，实际 %v", out)
	}
	if out := redactor.RedactTelemetryAttributes(unknown, map[string]string{"outcome": "ok"}); len(out) != 0 {
		t.Fatalf("未登记 operation 的埋点维度必须 fail-closed，实际 %v", out)
	}
}

func TestOperationPrivacyGeneratedTableCoversEveryDomain(t *testing.T) {
	redactor := NewOperationPrivacyRedactor()
	if got := len(redactor.OperationIDs()); got != generatedOperationPrivacyPolicyCount {
		t.Fatalf("派生表条目数=%d，与同次 codegen 计数=%d 不一致", got, generatedOperationPrivacyPolicyCount)
	}
	domains := map[string]int{}
	for _, operationID := range redactor.OperationIDs() {
		policy, _ := redactor.Policy(operationID)
		if policy.OperationID != operationID {
			t.Fatalf("%s: 派生表 key 与 OperationID 不一致（%s）", operationID, policy.OperationID)
		}
		if policy.Domain == "" || !strings.HasPrefix(operationID, policy.Domain+".") {
			t.Fatalf("%s: domain %q 与 operation id 不同源", operationID, policy.Domain)
		}
		if policy.Metric == "" {
			t.Fatalf("%s: 派生表缺少 telemetry.metric", operationID)
		}
		domains[policy.Domain]++
	}
	if len(domains) < 10 {
		t.Fatalf("派生表只覆盖 %d 个域，疑似 ContractGraph 读取不完整", len(domains))
	}
	t.Logf("operations=%d domains=%d", len(redactor.OperationIDs()), len(domains))
}

func TestOperationPrivacySecretOverridesRedactedPolicy(t *testing.T) {
	// 单元边界：SECRET + redacted 时不得退化成掩码保留，必须整条丢弃。
	redactor := newOperationPrivacyRedactorWith(map[string]OperationPrivacyPolicy{
		"user.session.IssueToken": {
			OperationID:            "user.session.IssueToken",
			Domain:                 "user",
			Metric:                 "user_session_issue_token",
			RequestClassification:  PrivacyClassInternal,
			ResponseClassification: PrivacyClassSecret,
			LogPolicy:              LogPolicyRedacted,
			TelemetryAttributes:    []string{"outcome"},
		},
	})
	out := redactor.RedactLogPayload(
		"user.session.IssueToken", PayloadResponse, map[string]any{"token": "secret"},
	)
	if len(out) != 0 {
		t.Fatalf("SECRET 响应必须整体丢弃，实际 %v", out)
	}
	in := redactor.RedactLogPayload(
		"user.session.IssueToken", PayloadRequest, map[string]any{"client_id": "app"},
	)
	if in["client_id"] != "app" {
		t.Fatalf("INTERNAL 请求在 redacted 下应原样保留，实际 %v", in)
	}
}
