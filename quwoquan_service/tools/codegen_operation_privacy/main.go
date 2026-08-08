// Command codegen_operation_privacy 从 ContractGraph 派生运行时脱敏表。
//
// `operation.privacy` 过去只存在于 schema 与契约 YAML 里：每个 operation 都声明了
// requestClassification / responseClassification / logPolicy，但没有任何端云运行时消费它，
// 等于「声明了隐私级别却不脱敏」。本工具把这三个字段派生成 Go 运行时可查的策略表，
// 由 quwoquan_service/runtime/observability 的 OperationPrivacyRedactor 在日志与埋点出口执行。
//
// 真相源只有统一 ContractGraph Source；产物带 -check 漂移检测。
package main

import (
	"bytes"
	"flag"
	"fmt"
	"go/format"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
)

var (
	classifications = map[string]bool{
		"PUBLIC": true, "INTERNAL": true, "SENSITIVE": true, "PII": true, "SECRET": true,
	}
	logPolicies = map[string]bool{"none": true, "metadata_only": true, "redacted": true}
)

func main() {
	metadataDir := flag.String("metadata-dir", "contracts/metadata", "metadata root directory")
	outputPath := flag.String(
		"output",
		filepath.Join("runtime", "observability", "operation_privacy_generated.go"),
		"generated runtime redaction table",
	)
	dartOutputPath := flag.String(
		"dart-output",
		"",
		"generated App runtime redaction table (empty disables Dart emission)",
	)
	check := flag.Bool("check", false, "fail when generated output is stale")
	flag.Parse()

	source, err := contractcodegen.NewSource(*metadataDir, validate.ProfileBaseline)
	exitIf(err)

	operations, err := normalize(source.Graph().Operations)
	exitIf(err)

	content, err := format.Source([]byte(render(operations)))
	exitIf(err)

	emissions := []emission{{path: *outputPath, content: content}}
	if strings.TrimSpace(*dartOutputPath) != "" {
		emissions = append(emissions, emission{
			path:    *dartOutputPath,
			content: []byte(renderDart(operations)),
		})
	}

	if *check {
		for _, item := range emissions {
			actual, readErr := os.ReadFile(item.path)
			if readErr != nil || !bytes.Equal(actual, item.content) {
				fmt.Fprintf(os.Stderr, "stale generated operation privacy table: %s\n", item.path)
				os.Exit(1)
			}
		}
		fmt.Printf("[operation-privacy] OK operations=%d outputs=%d\n", len(operations), len(emissions))
		return
	}
	for _, item := range emissions {
		exitIf(os.MkdirAll(filepath.Dir(item.path), 0o755))
		exitIf(os.WriteFile(item.path, item.content, 0o644))
		fmt.Printf("[operation-privacy] wrote %s operations=%d\n", item.path, len(operations))
	}
}

// emission 是同一份 operation.privacy 派生结果的一个语言产物。
// 端云两侧必须来自同一次 normalize，否则脱敏口径会在端云之间分叉。
type emission struct {
	path    string
	content []byte
}

// normalize 校验并排序 operation 隐私声明；任何缺失或非法取值都必须中断，
// 因为运行时脱敏一旦查不到策略就只能 fail-closed，静默放行等于泄漏。
func normalize(raw []ast.Operation) ([]ast.Operation, error) {
	seen := make(map[string]bool, len(raw))
	result := make([]ast.Operation, 0, len(raw))
	for _, item := range raw {
		if item.ID == "" {
			return nil, fmt.Errorf("ContractGraph operation 缺少 id")
		}
		if seen[item.ID] {
			return nil, fmt.Errorf("%s: operation id 重复", item.ID)
		}
		seen[item.ID] = true
		if !classifications[item.Privacy.RequestClassification] {
			return nil, fmt.Errorf(
				"%s: requestClassification %q 不是已声明取值",
				item.ID, item.Privacy.RequestClassification,
			)
		}
		if !classifications[item.Privacy.ResponseClassification] {
			return nil, fmt.Errorf(
				"%s: responseClassification %q 不是已声明取值",
				item.ID, item.Privacy.ResponseClassification,
			)
		}
		if !logPolicies[item.Privacy.LogPolicy] {
			return nil, fmt.Errorf("%s: logPolicy %q 不是已声明取值", item.ID, item.Privacy.LogPolicy)
		}
		if strings.TrimSpace(item.Telemetry.Metric) == "" {
			return nil, fmt.Errorf("%s: 缺少 telemetry.metric", item.ID)
		}
		attributes := append([]string(nil), item.Telemetry.Attributes...)
		sort.Strings(attributes)
		item.Telemetry.Attributes = attributes
		result = append(result, item)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].ID < result[j].ID })
	return result, nil
}

func render(operations []ast.Operation) string {
	var builder strings.Builder
	builder.WriteString("// Code generated from the unified ContractGraph source. DO NOT EDIT.\n")
	builder.WriteString("// Regenerate with: go run ./tools/codegen_operation_privacy\n\n")
	builder.WriteString("package runtimeobservability\n\n")
	builder.WriteString("// generatedOperationPrivacyPolicies 是 operation.privacy 的运行时投影。\n")
	builder.WriteString("// key 为 ContractGraph operation id；查不到即 fail-closed。\n")
	builder.WriteString("var generatedOperationPrivacyPolicies = map[string]OperationPrivacyPolicy{\n")
	for _, item := range operations {
		builder.WriteString(fmt.Sprintf("\t%q: {\n", item.ID))
		builder.WriteString(fmt.Sprintf("\t\tOperationID: %q,\n", item.ID))
		builder.WriteString(fmt.Sprintf("\t\tDomain: %q,\n", item.Domain))
		builder.WriteString(fmt.Sprintf("\t\tMetric: %q,\n", item.Telemetry.Metric))
		builder.WriteString(fmt.Sprintf(
			"\t\tRequestClassification: %s,\n", classConst(item.Privacy.RequestClassification),
		))
		builder.WriteString(fmt.Sprintf(
			"\t\tResponseClassification: %s,\n", classConst(item.Privacy.ResponseClassification),
		))
		builder.WriteString(fmt.Sprintf("\t\tLogPolicy: %s,\n", policyConst(item.Privacy.LogPolicy)))
		if len(item.Telemetry.Attributes) == 0 {
			builder.WriteString("\t\tTelemetryAttributes: nil,\n")
		} else {
			quoted := make([]string, 0, len(item.Telemetry.Attributes))
			for _, attribute := range item.Telemetry.Attributes {
				quoted = append(quoted, fmt.Sprintf("%q", attribute))
			}
			builder.WriteString(fmt.Sprintf(
				"\t\tTelemetryAttributes: []string{%s},\n", strings.Join(quoted, ", "),
			))
		}
		builder.WriteString("\t},\n")
	}
	builder.WriteString("}\n")
	return builder.String()
}

// renderDart 输出 App 侧运行时脱敏表。
//
// 与 Go 产物同源同序：端云对同一个 operation 必须得到同一个密级与 logPolicy，
// 否则「云侧脱敏、端侧原样上报」会让声明的隐私级别在端侧失效。
func renderDart(operations []ast.Operation) string {
	var builder strings.Builder
	builder.WriteString("// Code generated from the unified ContractGraph source. DO NOT EDIT.\n")
	builder.WriteString("// Regenerate with: make -C quwoquan_service codegen-operation-privacy\n\n")
	builder.WriteString("/// operation.privacy 声明的数据密级，按敏感度单调递增。\n")
	builder.WriteString("enum OperationPrivacyClass {\n")
	for _, name := range []string{"public", "internal", "sensitive", "pii", "secret"} {
		builder.WriteString(fmt.Sprintf("  %s,\n", name))
	}
	builder.WriteString("}\n\n")
	builder.WriteString("/// operation.privacy.logPolicy 声明的日志载荷策略。\n")
	builder.WriteString("enum OperationLogPolicy {\n")
	builder.WriteString("  /// 载荷完全不进日志。\n  none,\n")
	builder.WriteString("  /// 只保留键与形状元数据，值一律不落盘。\n  metadataOnly,\n")
	builder.WriteString("  /// 低密级值可落盘，高密级值必须掩码。\n  redacted,\n")
	builder.WriteString("}\n\n")
	builder.WriteString("/// 单个 operation 的运行时脱敏策略。\n")
	builder.WriteString("final class OperationPrivacyPolicy {\n")
	builder.WriteString("  const OperationPrivacyPolicy({\n")
	builder.WriteString("    required this.operationId,\n")
	builder.WriteString("    required this.domain,\n")
	builder.WriteString("    required this.metric,\n")
	builder.WriteString("    required this.requestClassification,\n")
	builder.WriteString("    required this.responseClassification,\n")
	builder.WriteString("    required this.logPolicy,\n")
	builder.WriteString("    required this.telemetryAttributes,\n")
	builder.WriteString("  });\n\n")
	builder.WriteString("  final String operationId;\n")
	builder.WriteString("  final String domain;\n")
	builder.WriteString("  final String metric;\n")
	builder.WriteString("  final OperationPrivacyClass requestClassification;\n")
	builder.WriteString("  final OperationPrivacyClass responseClassification;\n")
	builder.WriteString("  final OperationLogPolicy logPolicy;\n\n")
	builder.WriteString("  /// 契约声明的埋点维度白名单；埋点只允许出现这些键。\n")
	builder.WriteString("  final Set<String> telemetryAttributes;\n")
	builder.WriteString("}\n\n")
	builder.WriteString("/// operation.privacy 的端侧运行时投影。\n")
	builder.WriteString("/// key 为 ContractGraph operation id；查不到即 fail-closed。\n")
	builder.WriteString(
		"const Map<String, OperationPrivacyPolicy> generatedOperationPrivacyPolicies =\n",
	)
	builder.WriteString("    <String, OperationPrivacyPolicy>{\n")
	for _, item := range operations {
		builder.WriteString(fmt.Sprintf("  %s: OperationPrivacyPolicy(\n", dartQuote(item.ID)))
		builder.WriteString(fmt.Sprintf("    operationId: %s,\n", dartQuote(item.ID)))
		builder.WriteString(fmt.Sprintf("    domain: %s,\n", dartQuote(item.Domain)))
		builder.WriteString(fmt.Sprintf("    metric: %s,\n", dartQuote(item.Telemetry.Metric)))
		builder.WriteString(fmt.Sprintf(
			"    requestClassification: %s,\n", dartClassConst(item.Privacy.RequestClassification),
		))
		builder.WriteString(fmt.Sprintf(
			"    responseClassification: %s,\n", dartClassConst(item.Privacy.ResponseClassification),
		))
		builder.WriteString(fmt.Sprintf(
			"    logPolicy: %s,\n", dartPolicyConst(item.Privacy.LogPolicy),
		))
		if len(item.Telemetry.Attributes) == 0 {
			builder.WriteString("    telemetryAttributes: <String>{},\n")
		} else {
			quoted := make([]string, 0, len(item.Telemetry.Attributes))
			for _, attribute := range item.Telemetry.Attributes {
				quoted = append(quoted, dartQuote(attribute))
			}
			builder.WriteString(fmt.Sprintf(
				"    telemetryAttributes: <String>{%s},\n", strings.Join(quoted, ", "),
			))
		}
		builder.WriteString("  ),\n")
	}
	builder.WriteString("};\n")
	return builder.String()
}

func dartQuote(value string) string {
	replacer := strings.NewReplacer("\\", "\\\\", "'", "\\'", "$", "\\$", "\n", "\\n")
	return "'" + replacer.Replace(value) + "'"
}

func dartClassConst(value string) string {
	switch value {
	case "PUBLIC":
		return "OperationPrivacyClass.public"
	case "INTERNAL":
		return "OperationPrivacyClass.internal"
	case "SENSITIVE":
		return "OperationPrivacyClass.sensitive"
	case "PII":
		return "OperationPrivacyClass.pii"
	case "SECRET":
		return "OperationPrivacyClass.secret"
	}
	panic("unreachable classification " + value)
}

func dartPolicyConst(value string) string {
	switch value {
	case "none":
		return "OperationLogPolicy.none"
	case "metadata_only":
		return "OperationLogPolicy.metadataOnly"
	case "redacted":
		return "OperationLogPolicy.redacted"
	}
	panic("unreachable log policy " + value)
}

func classConst(value string) string {
	switch value {
	case "PUBLIC":
		return "PrivacyClassPublic"
	case "INTERNAL":
		return "PrivacyClassInternal"
	case "SENSITIVE":
		return "PrivacyClassSensitive"
	case "PII":
		return "PrivacyClassPII"
	case "SECRET":
		return "PrivacyClassSecret"
	}
	panic("unreachable classification " + value)
}

func policyConst(value string) string {
	switch value {
	case "none":
		return "LogPolicyNone"
	case "metadata_only":
		return "LogPolicyMetadataOnly"
	case "redacted":
		return "LogPolicyRedacted"
	}
	panic("unreachable log policy " + value)
}

func exitIf(err error) {
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
