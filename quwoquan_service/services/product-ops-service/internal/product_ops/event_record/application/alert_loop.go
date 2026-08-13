package application

import (
	"context"
	"fmt"
	"log"
	"sort"
	"strconv"
	"time"
)

// alert_loop 是 ES 聚合告警的运行时评估循环：
// 读聚合文档 -> 字段派生 -> 条件求值 -> 推送 Alertmanager v2。
// firing 告警每轮续期（endsAt = now + 冷却窗），停止命中后由 Alertmanager 自动 resolve。

// AlertAggregateReader 查询聚合索引中一个 rowKind 的窗口文档。
type AlertAggregateReader interface {
	ListAggregateAlertRows(
		ctx context.Context,
		rowKind string,
		from time.Time,
		to time.Time,
	) ([]map[string]any, error)
	// AggregateGeneratedThrough 返回聚合数据最大 generatedThrough 水位。
	AggregateGeneratedThrough(ctx context.Context) (time.Time, bool, error)
}

// AlertRetentionInspector 读取原始索引 ILM 实际保留天数。
type AlertRetentionInspector interface {
	RawRetentionDays(ctx context.Context) (int, error)
	RuntimeRawRetentionDays(ctx context.Context) (int, error)
}

// AlertmanagerAlert 是 Alertmanager v2 POST /api/v2/alerts 的单条负载。
type AlertmanagerAlert struct {
	Labels      map[string]string `json:"labels"`
	Annotations map[string]string `json:"annotations"`
	StartsAt    time.Time         `json:"startsAt"`
	EndsAt      time.Time         `json:"endsAt"`
}

// AlertNotifier 投递 firing 告警。
type AlertNotifier interface {
	PostAlerts(ctx context.Context, alerts []AlertmanagerAlert) error
}

type AlertEvaluationLoop struct {
	policy    AlertPolicy
	reader    AlertAggregateReader
	notifier  AlertNotifier
	retention AlertRetentionInspector
	interval  time.Duration
	now       func() time.Time
	logf      func(format string, args ...any)
}

func NewAlertEvaluationLoop(
	policy AlertPolicy,
	reader AlertAggregateReader,
	notifier AlertNotifier,
	retention AlertRetentionInspector,
	interval time.Duration,
) (*AlertEvaluationLoop, error) {
	if reader == nil || notifier == nil || retention == nil {
		return nil, fmt.Errorf("alert evaluation loop misses reader, notifier or retention inspector")
	}
	if interval <= 0 {
		interval = time.Minute
	}
	return &AlertEvaluationLoop{
		policy:    policy,
		reader:    reader,
		notifier:  notifier,
		retention: retention,
		interval:  interval,
		now:       time.Now,
		logf:      log.Printf,
	}, nil
}

func (loop *AlertEvaluationLoop) Run(ctx context.Context) {
	ticker := time.NewTicker(loop.interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if _, err := loop.RunOnce(ctx); err != nil {
				loop.logf("product-ops telemetry alert evaluation failed: %v", err)
			}
		}
	}
}

// RunOnce 执行一轮完整评估并返回 firing 集合（供测试与诊断）。
// 单条告警的派生/查询失败不会中断本轮：失败计入 failedTransformCount，
// 由 product-telemetry-transform-failed 告警自身外显。
func (loop *AlertEvaluationLoop) RunOnce(ctx context.Context) ([]FiringAlert, error) {
	now := loop.now().UTC()
	runtimeMetrics := loop.collectRuntimeMetrics(ctx, now)
	rowKindWindows := map[string]int{}
	for _, rule := range loop.policy.Alerts {
		if rule.RowKind == "control_plane" {
			continue
		}
		if rule.WindowMinutes > rowKindWindows[rule.RowKind] {
			rowKindWindows[rule.RowKind] = rule.WindowMinutes
		}
	}
	rowKinds := make([]string, 0, len(rowKindWindows))
	for rowKind := range rowKindWindows {
		rowKinds = append(rowKinds, rowKind)
	}
	sort.Strings(rowKinds)
	documentsByRowKind := map[string][]map[string]any{}
	for _, rowKind := range rowKinds {
		// 聚合行按 businessHour 桶存储：窗口起点向下对齐到小时桶边界。
		from := now.Add(-time.Duration(rowKindWindows[rowKind]) * time.Minute).
			Truncate(time.Hour)
		documents, err := loop.reader.ListAggregateAlertRows(ctx, rowKind, from, now)
		if err != nil {
			runtimeMetrics.FailedTransformCount++
			loop.logf(
				"product-ops telemetry alert rowKind %s query failed: %v",
				rowKind, err,
			)
			continue
		}
		documentsByRowKind[rowKind] = documents
	}
	firing := make([]FiringAlert, 0)
	// control_plane 告警最后评估，让本轮失败计数进入 failedTransformCount。
	deferred := make([]AlertRule, 0)
	for _, rule := range loop.policy.Alerts {
		if rule.RowKind == "control_plane" {
			deferred = append(deferred, rule)
			continue
		}
		documents := loop.windowedDocuments(
			documentsByRowKind[rule.RowKind], rule.WindowMinutes, now,
		)
		hits, err := EvaluateAlertRule(rule, documents, runtimeMetrics)
		if err != nil {
			runtimeMetrics.FailedTransformCount++
			loop.logf("product-ops telemetry alert %s evaluation failed: %v", rule.Name, err)
			continue
		}
		firing = append(firing, hits...)
	}
	for _, rule := range deferred {
		hits, err := EvaluateAlertRule(rule, nil, runtimeMetrics)
		if err != nil {
			loop.logf("product-ops telemetry alert %s evaluation failed: %v", rule.Name, err)
			continue
		}
		firing = append(firing, hits...)
	}
	if len(firing) > 0 {
		if err := loop.notifier.PostAlerts(ctx, loop.renderAlerts(firing, now)); err != nil {
			return firing, fmt.Errorf("post alerts to Alertmanager: %w", err)
		}
	}
	return firing, nil
}

func (loop *AlertEvaluationLoop) collectRuntimeMetrics(
	ctx context.Context,
	now time.Time,
) EvaluatorRuntimeMetrics {
	metrics := EvaluatorRuntimeMetrics{}
	generatedThrough, hasSamples, err := loop.reader.AggregateGeneratedThrough(ctx)
	switch {
	case err != nil:
		metrics.FailedTransformCount++
		loop.logf("product-ops telemetry aggregate freshness query failed: %v", err)
	case hasSamples:
		metrics.FreshnessMinutes = now.Sub(generatedThrough).Minutes()
	}
	if days, err := loop.retention.RawRetentionDays(ctx); err != nil {
		loop.logf("product-ops telemetry raw retention inspection failed: %v", err)
	} else {
		metrics.RawRetentionDays = &days
	}
	if days, err := loop.retention.RuntimeRawRetentionDays(ctx); err != nil {
		loop.logf("product-ops telemetry runtime retention inspection failed: %v", err)
	} else {
		metrics.RuntimeRawRetentionDays = &days
	}
	return metrics
}

func (loop *AlertEvaluationLoop) windowedDocuments(
	documents []map[string]any,
	windowMinutes int,
	now time.Time,
) []map[string]any {
	cutoff := now.Add(-time.Duration(windowMinutes) * time.Minute).
		Truncate(time.Hour).
		Format(time.RFC3339Nano)
	filtered := make([]map[string]any, 0, len(documents))
	for _, document := range documents {
		bucketStart, _ := document["bucketStart"].(string)
		if bucketStart >= cutoff {
			filtered = append(filtered, document)
		}
	}
	return filtered
}

func (loop *AlertEvaluationLoop) renderAlerts(
	firing []FiringAlert,
	now time.Time,
) []AlertmanagerAlert {
	alerts := make([]AlertmanagerAlert, 0, len(firing))
	for _, hit := range firing {
		labels := map[string]string{
			"alertname": hit.Rule.Name,
			"severity":  hit.Rule.Severity,
			"rowKind":   hit.Rule.RowKind,
			"source":    "product-ops-es-evaluator",
			"policy":    loop.policy.Name,
		}
		for dimension, value := range hit.GroupLabels {
			labels[dimension] = value
		}
		annotations := map[string]string{
			"condition": hit.Rule.ConditionRaw,
		}
		fieldNames := make([]string, 0, len(hit.FieldValues))
		for name := range hit.FieldValues {
			fieldNames = append(fieldNames, name)
		}
		sort.Strings(fieldNames)
		for _, name := range fieldNames {
			annotations["field_"+name] = strconv.FormatFloat(
				hit.FieldValues[name], 'f', -1, 64,
			)
		}
		alerts = append(alerts, AlertmanagerAlert{
			Labels:      labels,
			Annotations: annotations,
			StartsAt:    now,
			// 续期窗取评估间隔的 3 倍：漏一轮不抖动、连续漏两轮自动 resolve。
			EndsAt: now.Add(3 * loop.interval),
		})
	}
	return alerts
}
