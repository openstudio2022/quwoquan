package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"regexp"
	"strconv"
	"time"
)

// elasticsearch_alert_reader 为 ES 告警评估循环提供聚合行读取、
// 数据新鲜度水位与 ILM 实际保留天数（漂移检测用）。

const elasticsearchAlertRowLimit = 10000

func (s *ElasticsearchEventLogStore) ListAggregateAlertRows(
	ctx context.Context,
	rowKind string,
	from time.Time,
	to time.Time,
) ([]map[string]any, error) {
	var response struct {
		Hits struct {
			Total struct {
				Value int `json:"value"`
			} `json:"total"`
			Hits []struct {
				Source map[string]any `json:"_source"`
			} `json:"hits"`
		} `json:"hits"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.AggregateIndex), map[string]any{
		"size": elasticsearchAlertRowLimit,
		"query": map[string]any{
			"bool": map[string]any{
				"filter": []any{
					map[string]any{"term": map[string]any{"rowKind": rowKind}},
					elasticsearchRangeFilter("bucketStart", from, to),
				},
			},
		},
	}, &response); err != nil {
		return nil, fmt.Errorf(
			"query Elasticsearch aggregate alert rows for %s: %w",
			rowKind, err,
		)
	}
	if response.Hits.Total.Value > elasticsearchAlertRowLimit {
		return nil, fmt.Errorf(
			"aggregate alert rows for %s overflow evaluator limit: %d > %d",
			rowKind, response.Hits.Total.Value, elasticsearchAlertRowLimit,
		)
	}
	rows := make([]map[string]any, 0, len(response.Hits.Hits))
	for _, hit := range response.Hits.Hits {
		rows = append(rows, hit.Source)
	}
	return rows, nil
}

func (s *ElasticsearchEventLogStore) AggregateGeneratedThrough(
	ctx context.Context,
) (time.Time, bool, error) {
	var response struct {
		Aggregations struct {
			GeneratedThrough struct {
				ValueAsString string `json:"value_as_string"`
			} `json:"generated_through"`
		} `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.AggregateIndex), map[string]any{
		"size": 0,
		"aggs": map[string]any{
			"generated_through": map[string]any{
				"max": map[string]any{
					"field":  "generatedThrough",
					"format": "strict_date_optional_time_nanos",
				},
			},
		},
	}, &response); err != nil {
		return time.Time{}, false, fmt.Errorf(
			"query Elasticsearch aggregate freshness: %w",
			err,
		)
	}
	raw := response.Aggregations.GeneratedThrough.ValueAsString
	if raw == "" {
		return time.Time{}, false, nil
	}
	generatedThrough, err := time.Parse(time.RFC3339Nano, raw)
	if err != nil {
		return time.Time{}, false, fmt.Errorf(
			"decode Elasticsearch aggregate freshness %q: %w",
			raw, err,
		)
	}
	return generatedThrough.UTC(), true, nil
}

// RawRetentionDays / RuntimeRawRetentionDays 读取 Elasticsearch 端 ILM
// 策略的实际 delete min_age；与契约 3d 的漂移由告警外显。
// 两类原始索引共用 qwq-product-telemetry-raw-3d 策略，各自独立读取，
// 保证任一侧被改绑或改值时均能观测。
func (s *ElasticsearchEventLogStore) RawRetentionDays(ctx context.Context) (int, error) {
	return s.lifecycleRetentionDays(ctx, elasticsearchRawRetentionPolicy)
}

func (s *ElasticsearchEventLogStore) RuntimeRawRetentionDays(ctx context.Context) (int, error) {
	return s.lifecycleRetentionDays(ctx, elasticsearchRawRetentionPolicy)
}

var elasticsearchMinimumAgePattern = regexp.MustCompile(`^(\d+)d$`)

func (s *ElasticsearchEventLogStore) lifecycleRetentionDays(
	ctx context.Context,
	policy string,
) (int, error) {
	status, body, err := s.request(
		ctx,
		http.MethodGet,
		"/_ilm/policy/"+policy,
		nil,
		"application/json",
	)
	if err != nil {
		return 0, fmt.Errorf("read Elasticsearch lifecycle policy %s: %w", policy, err)
	}
	if status != http.StatusOK {
		return 0, fmt.Errorf(
			"read Elasticsearch lifecycle policy %s status=%d: %s",
			policy, status, truncateElasticsearchBody(body),
		)
	}
	var decoded map[string]struct {
		Policy struct {
			Phases struct {
				Delete struct {
					MinAge string `json:"min_age"`
				} `json:"delete"`
			} `json:"phases"`
		} `json:"policy"`
	}
	if err := json.Unmarshal(body, &decoded); err != nil {
		return 0, fmt.Errorf(
			"decode Elasticsearch lifecycle policy %s: %w",
			policy, err,
		)
	}
	entry, ok := decoded[policy]
	if !ok {
		return 0, fmt.Errorf("Elasticsearch lifecycle policy %s is absent", policy)
	}
	matches := elasticsearchMinimumAgePattern.FindStringSubmatch(
		entry.Policy.Phases.Delete.MinAge,
	)
	if matches == nil {
		return 0, fmt.Errorf(
			"Elasticsearch lifecycle policy %s min_age %q is not day-granular",
			policy, entry.Policy.Phases.Delete.MinAge,
		)
	}
	days, err := strconv.Atoi(matches[1])
	if err != nil {
		return 0, fmt.Errorf(
			"Elasticsearch lifecycle policy %s min_age %q: %w",
			policy, entry.Policy.Phases.Delete.MinAge, err,
		)
	}
	return days, nil
}
