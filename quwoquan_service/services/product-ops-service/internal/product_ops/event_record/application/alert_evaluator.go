package application

import (
	"fmt"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/domain"
)

// alert_evaluator 对窗口内的聚合文档执行 AlertRule 的字段派生与条件求值。
// 输入是聚合索引中的原样文档（rowKind 已由查询过滤），窗口按小时桶对齐：
// 聚合行粒度是 businessHour，窗口起点向下取整到桶边界。

// EvaluatorRuntimeMetrics 承载 control_plane 告警的评估器自产字段。
type EvaluatorRuntimeMetrics struct {
	// FailedTransformCount 是本评估周期内字段派生/查询失败次数。
	FailedTransformCount int
	// FreshnessMinutes 是 aggregate 最大 generatedThrough 距 now 的分钟数。
	FreshnessMinutes float64
	// RawRetentionDays / RuntimeRawRetentionDays 读自 Elasticsearch ILM 实际策略。
	RawRetentionDays        *int
	RuntimeRawRetentionDays *int
}

func (metrics EvaluatorRuntimeMetrics) lookup(name string) (float64, bool) {
	switch name {
	case "failedTransformCount":
		return float64(metrics.FailedTransformCount), true
	case "freshnessMinutes":
		return metrics.FreshnessMinutes, true
	case "rawRetentionDays":
		if metrics.RawRetentionDays == nil {
			return 0, false
		}
		return float64(*metrics.RawRetentionDays), true
	case "runtimeRawRetentionDays":
		if metrics.RuntimeRawRetentionDays == nil {
			return 0, false
		}
		return float64(*metrics.RuntimeRawRetentionDays), true
	default:
		return 0, false
	}
}

// FiringAlert 是一次条件命中的求值结果。
type FiringAlert struct {
	Rule        AlertRule
	GroupLabels map[string]string
	FieldValues map[string]float64
}

// EvaluateAlertRule 对文档执行 filter 过滤、group_by 分组、字段派生与条件求值。
func EvaluateAlertRule(
	rule AlertRule,
	documents []map[string]any,
	runtimeMetrics EvaluatorRuntimeMetrics,
) ([]FiringAlert, error) {
	groups := map[string][]map[string]any{}
	groupLabels := map[string]map[string]string{}
	if rule.RowKind == "control_plane" {
		groups[""] = nil
		groupLabels[""] = map[string]string{}
	}
	for _, document := range documents {
		if !rule.Filter.Evaluate(alertDocumentEnv(document)) {
			continue
		}
		key, labels := alertGroupKey(rule.GroupBy, document)
		groups[key] = append(groups[key], document)
		groupLabels[key] = labels
	}
	keys := make([]string, 0, len(groups))
	for key := range groups {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	firing := make([]FiringAlert, 0)
	for _, key := range keys {
		values, err := deriveAlertFields(rule, groups[key], runtimeMetrics)
		if err != nil {
			return nil, fmt.Errorf("alert %s group %q: %w", rule.Name, key, err)
		}
		if !rule.Condition.Evaluate(func(field string) (string, bool) {
			value, ok := values[field]
			if !ok {
				return "", false
			}
			return strconv.FormatFloat(value, 'f', -1, 64), true
		}) {
			continue
		}
		firing = append(firing, FiringAlert{
			Rule:        rule,
			GroupLabels: groupLabels[key],
			FieldValues: values,
		})
	}
	return firing, nil
}

func alertGroupKey(
	groupBy []string,
	document map[string]any,
) (string, map[string]string) {
	if len(groupBy) == 0 {
		return "", map[string]string{}
	}
	labels := make(map[string]string, len(groupBy))
	parts := make([]string, 0, len(groupBy))
	for _, dimension := range groupBy {
		value := alertDocumentString(document[dimension])
		labels[dimension] = value
		parts = append(parts, dimension+"="+value)
	}
	return strings.Join(parts, "\x1f"), labels
}

func deriveAlertFields(
	rule AlertRule,
	documents []map[string]any,
	runtimeMetrics EvaluatorRuntimeMetrics,
) (map[string]float64, error) {
	values := map[string]float64{}
	// div 依赖其他字段的求值结果：先算全部基础派生，再算比率。
	ordered := make([]AlertFieldDerivation, 0, len(rule.Fields))
	ratios := make([]AlertFieldDerivation, 0)
	for _, field := range rule.Fields {
		if field.Function == "div" {
			ratios = append(ratios, field)
			continue
		}
		ordered = append(ordered, field)
	}
	ordered = append(ordered, ratios...)
	for _, field := range ordered {
		switch field.Function {
		case "evaluator":
			if value, ok := runtimeMetrics.lookup(field.Argument); ok {
				values[field.Name] = value
			}
		case "sum":
			total := 0.0
			for _, document := range alertFilteredDocuments(documents, field.Where) {
				if value, ok := alertDocumentNumber(document[field.Argument]); ok {
					total += value
				}
			}
			values[field.Name] = total
		case "cardinality":
			distinct := map[string]struct{}{}
			for _, document := range alertFilteredDocuments(documents, field.Where) {
				hashes, ok := document[field.Argument].([]any)
				if !ok {
					if typed, isStrings := document[field.Argument].([]string); isStrings {
						for _, hash := range typed {
							distinct[hash] = struct{}{}
						}
					}
					continue
				}
				for _, hash := range hashes {
					distinct[alertDocumentString(hash)] = struct{}{}
				}
			}
			values[field.Name] = float64(len(distinct))
		case "p95", "hcount", "htailratio":
			merged, err := mergeAlertHistograms(
				alertFilteredDocuments(documents, field.Where), field.Argument,
			)
			if err != nil {
				return nil, fmt.Errorf("field %s: %w", field.Name, err)
			}
			switch field.Function {
			case "hcount":
				values[field.Name] = float64(merged.total)
			case "p95":
				if quantile, ok := merged.quantile(0.95); ok {
					values[field.Name] = quantile
				}
			case "htailratio":
				boundary, _ := strconv.Atoi(field.SecondArgument)
				if ratio, ok := merged.tailRatio(boundary); ok {
					values[field.Name] = ratio
				}
			}
		case "div":
			numerator, hasNumerator := values[field.Argument]
			denominator, hasDenominator := values[field.SecondArgument]
			if !hasNumerator || !hasDenominator || denominator == 0 {
				continue
			}
			values[field.Name] = numerator / denominator
		}
	}
	return values, nil
}

func alertFilteredDocuments(
	documents []map[string]any,
	where *domain.RollupCondition,
) []map[string]any {
	if where == nil {
		return documents
	}
	filtered := make([]map[string]any, 0, len(documents))
	for _, document := range documents {
		if where.Evaluate(alertDocumentEnv(document)) {
			filtered = append(filtered, document)
		}
	}
	return filtered
}

func alertDocumentEnv(document map[string]any) domain.ConditionEnv {
	return func(field string) (string, bool) {
		value, ok := document[field]
		if !ok {
			return "", false
		}
		text := alertDocumentString(value)
		return text, text != ""
	}
}

func alertDocumentString(value any) string {
	switch typed := value.(type) {
	case string:
		return typed
	case bool:
		return strconv.FormatBool(typed)
	case float64:
		return strconv.FormatFloat(typed, 'f', -1, 64)
	case int:
		return strconv.Itoa(typed)
	case int64:
		return strconv.FormatInt(typed, 10)
	case nil:
		return ""
	default:
		return fmt.Sprintf("%v", typed)
	}
}

func alertDocumentNumber(value any) (float64, bool) {
	switch typed := value.(type) {
	case float64:
		return typed, true
	case int:
		return float64(typed), true
	case int64:
		return float64(typed), true
	case string:
		parsed, err := strconv.ParseFloat(typed, 64)
		return parsed, err == nil
	default:
		return 0, false
	}
}

// mergedHistogram 是跨文档合并后的固定桶直方图（le 语义 + 末位 +Inf 桶）。
type mergedHistogram struct {
	bucketsMS []int
	counts    []int64
	total     int64
}

func mergeAlertHistograms(
	documents []map[string]any,
	field string,
) (mergedHistogram, error) {
	merged := mergedHistogram{}
	for _, document := range documents {
		raw, ok := document[field].(map[string]any)
		if !ok {
			continue
		}
		bucketsMS, err := alertIntSlice(raw["bucketsMs"])
		if err != nil {
			return mergedHistogram{}, fmt.Errorf("histogram %s buckets: %w", field, err)
		}
		counts, err := alertInt64Slice(raw["counts"])
		if err != nil {
			return mergedHistogram{}, fmt.Errorf("histogram %s counts: %w", field, err)
		}
		if len(counts) != len(bucketsMS)+1 {
			return mergedHistogram{}, fmt.Errorf(
				"histogram %s counts length %d does not close buckets length %d",
				field, len(counts), len(bucketsMS),
			)
		}
		if merged.bucketsMS == nil {
			merged.bucketsMS = bucketsMS
			merged.counts = make([]int64, len(counts))
		} else if !alertIntSliceEqual(merged.bucketsMS, bucketsMS) {
			return mergedHistogram{}, fmt.Errorf(
				"histogram %s bucket layouts diverge across documents", field,
			)
		}
		for index, count := range counts {
			merged.counts[index] += count
			merged.total += count
		}
	}
	return merged, nil
}

// quantile 用 Prometheus histogram_quantile 同款线性插值；样本为空时返回 false。
func (histogram mergedHistogram) quantile(q float64) (float64, bool) {
	if histogram.total == 0 {
		return 0, false
	}
	rank := q * float64(histogram.total)
	cumulative := int64(0)
	for index, count := range histogram.counts {
		cumulative += count
		if float64(cumulative) < rank {
			continue
		}
		if index >= len(histogram.bucketsMS) {
			// +Inf 桶：返回最高有限边界（保守上限）。
			return float64(histogram.bucketsMS[len(histogram.bucketsMS)-1]), true
		}
		lower := 0.0
		if index > 0 {
			lower = float64(histogram.bucketsMS[index-1])
		}
		upper := float64(histogram.bucketsMS[index])
		previousCumulative := cumulative - count
		if count == 0 {
			return upper, true
		}
		fraction := (rank - float64(previousCumulative)) / float64(count)
		return lower + (upper-lower)*fraction, true
	}
	return float64(histogram.bucketsMS[len(histogram.bucketsMS)-1]), true
}

// tailRatio 返回值 > boundaryMS 的样本占比；样本为空时返回 false。
func (histogram mergedHistogram) tailRatio(boundaryMS int) (float64, bool) {
	if histogram.total == 0 {
		return 0, false
	}
	tail := int64(0)
	for index, count := range histogram.counts {
		if index >= len(histogram.bucketsMS) || histogram.bucketsMS[index] > boundaryMS {
			tail += count
		}
	}
	return float64(tail) / float64(histogram.total), true
}

func alertIntSlice(value any) ([]int, error) {
	switch typed := value.(type) {
	case []int:
		return typed, nil
	case []any:
		out := make([]int, 0, len(typed))
		for _, item := range typed {
			number, ok := alertDocumentNumber(item)
			if !ok {
				return nil, fmt.Errorf("non-numeric entry %v", item)
			}
			out = append(out, int(number))
		}
		return out, nil
	default:
		return nil, fmt.Errorf("unexpected slice payload %T", value)
	}
}

func alertInt64Slice(value any) ([]int64, error) {
	switch typed := value.(type) {
	case []int64:
		return typed, nil
	case []any:
		out := make([]int64, 0, len(typed))
		for _, item := range typed {
			number, ok := alertDocumentNumber(item)
			if !ok {
				return nil, fmt.Errorf("non-numeric entry %v", item)
			}
			out = append(out, int64(number))
		}
		return out, nil
	default:
		return nil, fmt.Errorf("unexpected slice payload %T", value)
	}
}

func alertIntSliceEqual(a, b []int) bool {
	if len(a) != len(b) {
		return false
	}
	for index := range a {
		if a[index] != b[index] {
			return false
		}
	}
	return true
}
