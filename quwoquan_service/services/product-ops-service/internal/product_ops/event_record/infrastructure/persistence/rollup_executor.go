package persistence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/domain"
)

// rollup_executor 是 rollups.yaml（经 codegen 的 RollupCatalog）唯一的写侧执行器。
// 13 个 rowKind 全部由同一代数循环产出；禁止再为单个 rowKind 手写聚合分支。

type compiledRollupMeasure struct {
	generated.RollupMeasure
	where *domain.RollupCondition
}

type compiledRollupJob struct {
	generated.RollupJob
	filter   *domain.RollupCondition
	measures []compiledRollupMeasure
}

var (
	compiledRollupPlanOnce sync.Once
	compiledRollupPlan     []compiledRollupJob
	compiledRollupPlanErr  error
)

func rollupPlan() ([]compiledRollupJob, error) {
	compiledRollupPlanOnce.Do(func() {
		plan := make([]compiledRollupJob, 0, len(generated.RollupCatalog))
		for _, job := range generated.RollupCatalog {
			filter, err := domain.ParseRollupCondition(job.Filter)
			if err != nil {
				compiledRollupPlanErr = fmt.Errorf("rollup %s filter: %w", job.RowKind, err)
				return
			}
			compiled := compiledRollupJob{RollupJob: job, filter: filter}
			for _, measure := range job.Measures {
				where, err := domain.ParseRollupCondition(measure.Where)
				if err != nil {
					compiledRollupPlanErr = fmt.Errorf(
						"rollup %s measure %s: %w", job.RowKind, measure.Name, err,
					)
					return
				}
				compiled.measures = append(compiled.measures, compiledRollupMeasure{
					RollupMeasure: measure,
					where:         where,
				})
			}
			plan = append(plan, compiled)
		}
		compiledRollupPlan = plan
	})
	return compiledRollupPlan, compiledRollupPlanErr
}

type rollupHistogramState struct {
	counts []int64
	sum    int64
	total  int64
}

type rollupAccumulator struct {
	source           map[string]any
	counters         map[string]int64
	sums             map[string]float64
	hashSets         map[string]map[string]struct{}
	histograms       map[string]*rollupHistogramState
	generatedThrough string
}

// buildContractRollupDocuments 对一批记录执行全部匹配 source 的 rollup job。
// fieldsRows 内每行是 wire 字段的字符串视图；行身份在批内唯一，因此
// count_distinct_row_identity 在批内退化为行计数，跨批去重由含 batchKey 的
// 文档 ID 与 duplicate_policy 承载。
func buildContractRollupDocuments(
	index string,
	batchKey string,
	sourceKind string,
	idPrefix string,
	rows []rollupSourceRow,
) ([]elasticsearchBulkDocument, error) {
	plan, err := rollupPlan()
	if err != nil {
		return nil, err
	}
	type jobGroups struct {
		job    compiledRollupJob
		groups map[string]*rollupAccumulator
	}
	executions := make([]*jobGroups, 0, len(plan))
	for _, job := range plan {
		if job.Source != sourceKind {
			continue
		}
		executions = append(executions, &jobGroups{
			job:    job,
			groups: map[string]*rollupAccumulator{},
		})
	}
	for _, row := range rows {
		occurredAt, err := time.Parse(time.RFC3339Nano, row.fields["occurredAt"])
		if err != nil {
			return nil, fmt.Errorf(
				"parse %s occurredAt for Elasticsearch rollup: %w",
				sourceKind, err,
			)
		}
		bucketStart := occurredAt.UTC().Truncate(time.Hour).Format(time.RFC3339Nano)
		env := rollupFieldEnv(row.fields)
		generatedThrough := row.ingestedAt.UTC().Format(time.RFC3339Nano)
		for _, execution := range executions {
			if !execution.job.filter.Evaluate(env) {
				continue
			}
			accumulator := resolveRollupGroup(
				execution.groups, execution.job.RollupJob, row.fields, bucketStart,
			)
			if generatedThrough > accumulator.generatedThrough {
				accumulator.generatedThrough = generatedThrough
			}
			for _, measure := range execution.job.measures {
				applyRollupMeasure(accumulator, measure, row.fields, env)
			}
		}
	}
	documents := make([]elasticsearchBulkDocument, 0)
	for _, execution := range executions {
		keys := make([]string, 0, len(execution.groups))
		for key := range execution.groups {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		identityFields := append(
			[]string{"rowKind", "bucketStart"},
			execution.job.Dimensions...,
		)
		for _, key := range keys {
			accumulator := execution.groups[key]
			source := accumulator.source
			source["generatedThrough"] = accumulator.generatedThrough
			flushRollupMeasures(source, execution.job.measures, accumulator)
			targetIndex, err := dailyElasticsearchIndex(
				index, source["bucketStart"].(string),
			)
			if err != nil {
				return nil, fmt.Errorf(
					"resolve Elasticsearch %s aggregate index: %w",
					execution.job.RowKind, err,
				)
			}
			documents = append(documents, elasticsearchBulkDocument{
				Index:  targetIndex,
				ID:     rollupDocumentID(idPrefix, batchKey, source, identityFields),
				Source: source,
			})
		}
	}
	return documents, nil
}

type rollupSourceRow struct {
	fields     map[string]string
	ingestedAt time.Time
}

func rollupFieldEnv(fields map[string]string) domain.ConditionEnv {
	return func(field string) (string, bool) {
		value, ok := fields[field]
		return value, ok && value != ""
	}
}

func resolveRollupGroup(
	groups map[string]*rollupAccumulator,
	job generated.RollupJob,
	fields map[string]string,
	bucketStart string,
) *rollupAccumulator {
	keyParts := make([]string, 0, len(job.Dimensions)+1)
	keyParts = append(keyParts, bucketStart)
	source := map[string]any{
		"rowKind":     job.RowKind,
		"bucketStart": bucketStart,
	}
	for _, dimension := range job.Dimensions {
		value := fields[dimension]
		source[dimension] = value
		keyParts = append(keyParts, dimension+"="+value)
	}
	key := strings.Join(keyParts, "\x1f")
	accumulator := groups[key]
	if accumulator == nil {
		accumulator = &rollupAccumulator{
			source:     source,
			counters:   map[string]int64{},
			sums:       map[string]float64{},
			hashSets:   map[string]map[string]struct{}{},
			histograms: map[string]*rollupHistogramState{},
		}
		groups[key] = accumulator
	}
	return accumulator
}

func applyRollupMeasure(
	accumulator *rollupAccumulator,
	measure compiledRollupMeasure,
	fields map[string]string,
	env domain.ConditionEnv,
) {
	switch measure.Kind {
	case "count_distinct_row_identity":
		accumulator.counters[measure.Name]++
	case "count_distinct_row_identity_where":
		if measure.where.Evaluate(env) {
			accumulator.counters[measure.Name]++
		}
	case "sum":
		if value, ok := rollupNumericField(fields, measure.Field); ok {
			accumulator.sums[measure.Name] += value
		}
	case "mergeable_hll", "count_distinct_where":
		if measure.Kind == "count_distinct_where" && !measure.where.Evaluate(env) {
			return
		}
		raw := fields[measure.Field]
		if raw == "" {
			return
		}
		set := accumulator.hashSets[measure.Name]
		if set == nil {
			set = map[string]struct{}{}
			accumulator.hashSets[measure.Name] = set
		}
		digest := sha256.Sum256([]byte(raw))
		set[hex.EncodeToString(digest[:])] = struct{}{}
	case "fixed_histogram", "fixed_histogram_where":
		if measure.Kind == "fixed_histogram_where" && !measure.where.Evaluate(env) {
			return
		}
		value, ok := rollupNumericField(fields, measure.Field)
		if !ok {
			return
		}
		state := accumulator.histograms[measure.Name]
		if state == nil {
			state = &rollupHistogramState{
				counts: make([]int64, len(measure.BucketsMS)+1),
			}
			accumulator.histograms[measure.Name] = state
		}
		state.counts[rollupHistogramBucket(measure.BucketsMS, value)]++
		state.sum += int64(value)
		state.total++
	}
}

// rollupHistogramBucket 返回值应计入的桶下标：
// counts[i] 表示 value <= bucketsMs[i]（Prometheus le 语义），
// 末位 counts[len(bucketsMs)] 是 +Inf 桶。
func rollupHistogramBucket(bucketsMS []int, value float64) int {
	for index, upper := range bucketsMS {
		if value <= float64(upper) {
			return index
		}
	}
	return len(bucketsMS)
}

func rollupNumericField(fields map[string]string, field string) (float64, bool) {
	raw, ok := fields[field]
	if !ok || raw == "" {
		return 0, false
	}
	value, err := strconv.ParseFloat(raw, 64)
	if err != nil {
		return 0, false
	}
	return value, true
}

func flushRollupMeasures(
	source map[string]any,
	measures []compiledRollupMeasure,
	accumulator *rollupAccumulator,
) {
	for _, measure := range measures {
		switch measure.Kind {
		case "count_distinct_row_identity", "count_distinct_row_identity_where":
			source[measure.Name] = accumulator.counters[measure.Name]
		case "sum":
			total := accumulator.sums[measure.Name]
			if total == math.Trunc(total) {
				source[measure.Name] = int64(total)
			} else {
				source[measure.Name] = total
			}
		case "mergeable_hll", "count_distinct_where":
			hashes := make([]string, 0, len(accumulator.hashSets[measure.Name]))
			for hash := range accumulator.hashSets[measure.Name] {
				hashes = append(hashes, hash)
			}
			sort.Strings(hashes)
			source[rollupHashFieldName(measure.Name)] = hashes
			if measure.Kind == "count_distinct_where" {
				source[measure.Name] = int64(len(hashes))
			}
		case "fixed_histogram", "fixed_histogram_where":
			state := accumulator.histograms[measure.Name]
			if state == nil {
				state = &rollupHistogramState{
					counts: make([]int64, len(measure.BucketsMS)+1),
				}
			}
			source[measure.Name] = map[string]any{
				"bucketsMs": measure.BucketsMS,
				"counts":    state.counts,
				"sum":       state.sum,
				"count":     state.total,
			}
		}
	}
}

// rollupHashFieldName 保持既有读侧字段：sessionHll -> sessionHashes；
// 其余去重度量输出 <name>Hashes，读侧统一用 cardinality 合并跨文档基数。
func rollupHashFieldName(measureName string) string {
	if strings.HasSuffix(measureName, "Hll") {
		return strings.TrimSuffix(measureName, "Hll") + "Hashes"
	}
	return measureName + "Hashes"
}

// RollupDocumentIdentityFields 暴露给测试与评估器对齐文档身份。
func rollupDocumentIdentityJSON(source map[string]any, fields []string) string {
	group := make(map[string]any, len(fields))
	for _, field := range fields {
		group[field] = source[field]
	}
	canonical, _ := json.Marshal(group)
	return string(canonical)
}
