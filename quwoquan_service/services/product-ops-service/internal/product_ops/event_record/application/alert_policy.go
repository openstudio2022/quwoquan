package application

import (
	"fmt"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/domain"
)

// alert_policy 解析 quwoquan_ops/observability/elasticsearch/product_telemetry_alerts.yaml
// 的执行策略。策略文件是唯一真相源：condition 引用的每个字段都必须由 fields
// 显式派生，解析期完成闭合校验，运行期不允许任何隐式字段映射。

type AlertPolicy struct {
	Name   string
	Alerts []AlertRule
}

type AlertRule struct {
	Name          string
	RowKind       string
	Severity      string
	WindowMinutes int
	GroupBy       []string
	Filter        *domain.RollupCondition
	FilterSource  map[string]string
	Fields        []AlertFieldDerivation
	Condition     *domain.RollupCondition
	ConditionRaw  string
}

// AlertFieldDerivation 是一个 condition 字段的显式派生声明。
type AlertFieldDerivation struct {
	Name string
	// Function: sum | p95 | hcount | htailratio | cardinality | div | evaluator
	Function string
	Argument string
	// SecondArgument 供 div 的分母字段与 htailratio 的毫秒边界使用。
	SecondArgument string
	Where          *domain.RollupCondition
}

type alertPolicyFile struct {
	Metadata struct {
		Name string `yaml:"name"`
	} `yaml:"metadata"`
	Spec struct {
		Alerts []struct {
			Name          string            `yaml:"name"`
			RowKind       string            `yaml:"rowKind"`
			Severity      string            `yaml:"severity"`
			WindowMinutes int               `yaml:"window_minutes"`
			GroupBy       []string          `yaml:"group_by"`
			Filter        map[string]any    `yaml:"filter"`
			Fields        map[string]string `yaml:"fields"`
			Condition     string            `yaml:"condition"`
		} `yaml:"alerts"`
	} `yaml:"spec"`
}

var alertFieldExpressionPattern = regexp.MustCompile(
	`^([a-z][a-z0-9]*)\(([^)]*)\)(?:\s+where\s+(.+))?$`,
)

// conditionFieldPattern 提取 condition 中引用的字段名（首个标识符位置）。
var conditionFieldPattern = regexp.MustCompile(`(?:^|\(|AND\s+|OR\s+)\s*([A-Za-z][A-Za-z0-9]*)`)

func ParseAlertPolicy(raw []byte) (AlertPolicy, error) {
	var file alertPolicyFile
	if err := yaml.Unmarshal(raw, &file); err != nil {
		return AlertPolicy{}, fmt.Errorf("decode alert policy: %w", err)
	}
	policy := AlertPolicy{Name: file.Metadata.Name}
	seen := map[string]bool{}
	for _, entry := range file.Spec.Alerts {
		if entry.Name == "" || seen[entry.Name] {
			return AlertPolicy{}, fmt.Errorf(
				"alert name must be non-empty and unique: %q", entry.Name,
			)
		}
		seen[entry.Name] = true
		if entry.RowKind == "" || entry.Severity == "" || entry.Condition == "" {
			return AlertPolicy{}, fmt.Errorf(
				"alert %s misses rowKind, severity or condition", entry.Name,
			)
		}
		if entry.WindowMinutes <= 0 {
			return AlertPolicy{}, fmt.Errorf(
				"alert %s must declare a positive window_minutes", entry.Name,
			)
		}
		rule := AlertRule{
			Name:          entry.Name,
			RowKind:       entry.RowKind,
			Severity:      entry.Severity,
			WindowMinutes: entry.WindowMinutes,
			GroupBy:       entry.GroupBy,
			ConditionRaw:  entry.Condition,
		}
		filterCondition, filterSource, err := alertFilterCondition(entry.Filter)
		if err != nil {
			return AlertPolicy{}, fmt.Errorf("alert %s: %w", entry.Name, err)
		}
		rule.Filter = filterCondition
		rule.FilterSource = filterSource
		condition, err := domain.ParseRollupCondition(entry.Condition)
		if err != nil {
			return AlertPolicy{}, fmt.Errorf("alert %s: %w", entry.Name, err)
		}
		rule.Condition = condition
		fieldNames := make([]string, 0, len(entry.Fields))
		for name := range entry.Fields {
			fieldNames = append(fieldNames, name)
		}
		sort.Strings(fieldNames)
		declared := map[string]bool{}
		for _, name := range fieldNames {
			derivation, err := parseAlertFieldDerivation(name, entry.Fields[name])
			if err != nil {
				return AlertPolicy{}, fmt.Errorf("alert %s: %w", entry.Name, err)
			}
			rule.Fields = append(rule.Fields, derivation)
			declared[name] = true
		}
		// div 引用的字段必须先声明；condition 引用的字段必须全部被声明。
		for _, field := range rule.Fields {
			if field.Function != "div" {
				continue
			}
			if !declared[field.Argument] || !declared[field.SecondArgument] {
				return AlertPolicy{}, fmt.Errorf(
					"alert %s field %s divides undeclared fields",
					entry.Name, field.Name,
				)
			}
		}
		for _, referenced := range conditionFieldNames(entry.Condition) {
			if !declared[referenced] {
				return AlertPolicy{}, fmt.Errorf(
					"alert %s condition references underived field %q",
					entry.Name, referenced,
				)
			}
		}
		policy.Alerts = append(policy.Alerts, rule)
	}
	if len(policy.Alerts) == 0 {
		return AlertPolicy{}, fmt.Errorf("alert policy declares no alerts")
	}
	return policy, nil
}

// alertFilterCondition 把声明式 filter map 规范化为条件：
// excludeResult: X 表示 result != X，其余键是维度等值匹配。
func alertFilterCondition(
	filter map[string]any,
) (*domain.RollupCondition, map[string]string, error) {
	if len(filter) == 0 {
		empty, _ := domain.ParseRollupCondition("")
		return empty, map[string]string{}, nil
	}
	keys := make([]string, 0, len(filter))
	for key := range filter {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	source := make(map[string]string, len(filter))
	clauses := make([]string, 0, len(filter))
	for _, key := range keys {
		value := alertFilterValueString(filter[key])
		source[key] = value
		if key == "excludeResult" {
			clauses = append(clauses, "result != "+value)
			continue
		}
		clauses = append(clauses, key+" = "+value)
	}
	condition, err := domain.ParseRollupCondition(strings.Join(clauses, " AND "))
	if err != nil {
		return nil, nil, fmt.Errorf("normalize filter: %w", err)
	}
	return condition, source, nil
}

func alertFilterValueString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case bool:
		return strconv.FormatBool(typed)
	case int:
		return strconv.Itoa(typed)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	default:
		return fmt.Sprintf("%v", typed)
	}
}

func parseAlertFieldDerivation(name, expression string) (AlertFieldDerivation, error) {
	matches := alertFieldExpressionPattern.FindStringSubmatch(strings.TrimSpace(expression))
	if matches == nil {
		return AlertFieldDerivation{}, fmt.Errorf(
			"field %s has unparseable derivation %q", name, expression,
		)
	}
	derivation := AlertFieldDerivation{Name: name, Function: matches[1]}
	arguments := strings.Split(matches[2], ",")
	for index := range arguments {
		arguments[index] = strings.TrimSpace(arguments[index])
	}
	switch derivation.Function {
	case "sum", "p95", "hcount", "cardinality", "evaluator":
		if len(arguments) != 1 || arguments[0] == "" {
			return AlertFieldDerivation{}, fmt.Errorf(
				"field %s: %s takes exactly one argument", name, derivation.Function,
			)
		}
		derivation.Argument = arguments[0]
	case "div", "htailratio":
		if len(arguments) != 2 || arguments[0] == "" || arguments[1] == "" {
			return AlertFieldDerivation{}, fmt.Errorf(
				"field %s: %s takes exactly two arguments", name, derivation.Function,
			)
		}
		derivation.Argument = arguments[0]
		derivation.SecondArgument = arguments[1]
		if derivation.Function == "htailratio" {
			if _, err := strconv.Atoi(derivation.SecondArgument); err != nil {
				return AlertFieldDerivation{}, fmt.Errorf(
					"field %s: htailratio boundary must be integer milliseconds", name,
				)
			}
		}
	default:
		return AlertFieldDerivation{}, fmt.Errorf(
			"field %s uses unsupported derivation %q", name, derivation.Function,
		)
	}
	if matches[3] != "" {
		if derivation.Function == "div" || derivation.Function == "evaluator" {
			return AlertFieldDerivation{}, fmt.Errorf(
				"field %s: %s does not accept a where clause", name, derivation.Function,
			)
		}
		where, err := domain.ParseRollupCondition(matches[3])
		if err != nil {
			return AlertFieldDerivation{}, fmt.Errorf("field %s: %w", name, err)
		}
		derivation.Where = where
	}
	return derivation, nil
}

func conditionFieldNames(condition string) []string {
	names := map[string]bool{}
	for _, match := range conditionFieldPattern.FindAllStringSubmatch(condition, -1) {
		token := match[1]
		if token == "AND" || token == "OR" || token == "IS" ||
			token == "NOT" || token == "NULL" || token == "IN" ||
			token == "true" || token == "false" {
			continue
		}
		names[token] = true
	}
	out := make([]string, 0, len(names))
	for name := range names {
		out = append(out, name)
	}
	sort.Strings(out)
	return out
}
