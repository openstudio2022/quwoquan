package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"strconv"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

type elasticsearchHits struct {
	Total struct {
		Value int64 `json:"value"`
	} `json:"total"`
	Hits []struct {
		ID     string         `json:"_id"`
		Source map[string]any `json:"_source"`
	} `json:"hits"`
}

type elasticsearchMaxMetric struct {
	Value         *float64 `json:"value"`
	ValueAsString string   `json:"value_as_string"`
}

func (s *ElasticsearchEventLogStore) GetEventSummary(
	ctx context.Context,
	query application.EventSummaryQuery,
) (application.EventSummary, error) {
	dimensions := []string{
		"logType",
		"eventType",
		"pageName",
		"appVersion",
		"networkClass",
		"deviceManufacturer",
		"deviceModel",
		"journey",
		"action",
		"result",
		"errorCode",
	}
	filters := []any{
		map[string]any{"term": map[string]any{"rowKind": "event_dimensions"}},
		elasticsearchRangeFilter("bucketStart", query.From, query.To),
	}
	for field, value := range map[string]string{
		"logType":      query.LogType,
		"eventType":    query.EventType,
		"pageName":     query.PageName,
		"appVersion":   query.AppVersion,
		"networkClass": query.NetworkClass,
		"result":       query.Result,
		"errorCode":    query.ErrorCode,
	} {
		if value != "" {
			filters = append(
				filters,
				map[string]any{"term": map[string]any{field: value}},
			)
		}
	}
	aggregations := map[string]any{
		"total_count": map[string]any{"sum": map[string]any{"field": "count"}},
		"session_count": map[string]any{
			"cardinality": map[string]any{
				"field":               "sessionHashes",
				"precision_threshold": 40000,
			},
		},
		"generated_through": map[string]any{
			"max": map[string]any{
				"field":  "generatedThrough",
				"format": "strict_date_optional_time_nanos",
			},
		},
	}
	for _, field := range dimensions {
		aggregations["dimension_"+field] = map[string]any{
			"terms": map[string]any{"field": field, "size": 500},
			"aggs": map[string]any{
				"weighted_count": map[string]any{
					"sum": map[string]any{"field": "count"},
				},
			},
		}
	}
	var response struct {
		Aggregations map[string]json.RawMessage `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.AggregateIndex), map[string]any{
		"size":  0,
		"query": map[string]any{"bool": map[string]any{"filter": filters}},
		"aggs":  aggregations,
	}, &response); err != nil {
		return application.EventSummary{}, fmt.Errorf(
			"query Elasticsearch event aggregate: %w",
			err,
		)
	}
	out := application.EventSummary{
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "hourly_rollup",
		Freshness:         "no_samples",
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	out.TotalCount = int64(math.Round(
		elasticsearchMetricValue(response.Aggregations["total_count"]),
	))
	out.SessionCount = int64(math.Round(
		elasticsearchMetricValue(response.Aggregations["session_count"]),
	))
	for _, field := range dimensions {
		counts, err := elasticsearchDimensionCounts(
			response.Aggregations["dimension_"+field],
		)
		if err != nil {
			return application.EventSummary{}, fmt.Errorf(
				"decode Elasticsearch event dimension %s: %w",
				field,
				err,
			)
		}
		if len(counts) > 0 {
			out.DimensionCounters[field] = counts
		}
	}
	applyElasticsearchWaterline(
		&out.Freshness,
		&out.GeneratedThrough,
		&out.LagSeconds,
		response.Aggregations["generated_through"],
		s.now().UTC(),
		"near_realtime",
	)
	return out, nil
}

func (s *ElasticsearchEventLogStore) GetRuntimeLogSummary(
	ctx context.Context,
	query application.RuntimeLogSummaryQuery,
) (application.RuntimeLogSummary, error) {
	dimensions := []string{
		"logKind",
		"severity",
		"signal",
		"errorCode",
		"fingerprint",
		"resourceSourceType",
		"resourceService",
		"resourceAppVersion",
	}
	filters := []any{
		map[string]any{"term": map[string]any{"rowKind": "runtime_diagnostics"}},
		elasticsearchRangeFilter("bucketStart", query.From, query.To),
	}
	for field, value := range map[string]string{
		"signal":             query.Signal,
		"severity":           query.Severity,
		"errorCode":          query.ErrorCode,
		"fingerprint":        query.Fingerprint,
		"resourceSourceType": query.SourceType,
		"resourceService":    query.Service,
		"resourceAppVersion": query.AppVersion,
	} {
		if value != "" {
			filters = append(
				filters,
				map[string]any{"term": map[string]any{field: value}},
			)
		}
	}
	aggregations := map[string]any{
		"total_count": map[string]any{"sum": map[string]any{"field": "count"}},
		"generated_through": map[string]any{
			"max": map[string]any{
				"field":  "generatedThrough",
				"format": "strict_date_optional_time_nanos",
			},
		},
	}
	for _, field := range dimensions {
		aggregations["dimension_"+field] = map[string]any{
			"terms": map[string]any{"field": field, "size": 500},
			"aggs": map[string]any{
				"weighted_count": map[string]any{
					"sum": map[string]any{"field": "count"},
				},
			},
		}
	}
	var response struct {
		Aggregations map[string]json.RawMessage `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.AggregateIndex), map[string]any{
		"size":  0,
		"query": map[string]any{"bool": map[string]any{"filter": filters}},
		"aggs":  aggregations,
	}, &response); err != nil {
		return application.RuntimeLogSummary{}, fmt.Errorf(
			"query Elasticsearch runtime aggregate: %w",
			err,
		)
	}
	out := application.RuntimeLogSummary{
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "hourly_rollup",
		Freshness:         "no_samples",
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	out.TotalCount = int64(math.Round(
		elasticsearchMetricValue(response.Aggregations["total_count"]),
	))
	for _, field := range dimensions {
		counts, err := elasticsearchDimensionCounts(
			response.Aggregations["dimension_"+field],
		)
		if err != nil {
			return application.RuntimeLogSummary{}, fmt.Errorf(
				"decode Elasticsearch runtime dimension %s: %w",
				field,
				err,
			)
		}
		if len(counts) > 0 {
			out.DimensionCounters[field] = counts
		}
	}
	applyElasticsearchWaterline(
		&out.Freshness,
		&out.GeneratedThrough,
		&out.LagSeconds,
		response.Aggregations["generated_through"],
		s.now().UTC(),
		"near_realtime",
	)
	return out, nil
}

func (s *ElasticsearchEventLogStore) GetEventDrilldown(
	ctx context.Context,
	query application.EventDrilldownQuery,
) (application.EventDrilldown, error) {
	filters := []any{elasticsearchRangeFilter("occurredAt", query.From, query.To)}
	for field, value := range map[string]string{
		"logType":      query.LogType,
		"eventType":    query.EventType,
		"pageName":     query.PageName,
		"appVersion":   query.AppVersion,
		"networkClass": query.NetworkClass,
		"result":       query.Result,
		"errorCode":    query.ErrorCode,
		"sessionId":    query.SessionID,
	} {
		if value != "" {
			filters = append(
				filters,
				map[string]any{"term": map[string]any{field: value}},
			)
		}
	}
	var response struct {
		Hits elasticsearchHits `json:"hits"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
		"size":             query.Limit,
		"track_total_hits": true,
		"query":            map[string]any{"bool": map[string]any{"filter": filters}},
		"sort":             []any{map[string]any{"occurredAt": "desc"}},
	}, &response); err != nil {
		return application.EventDrilldown{}, fmt.Errorf(
			"query Elasticsearch event raw records: %w",
			err,
		)
	}
	rows := make([]map[string]string, 0, len(response.Hits.Hits))
	items := make([]application.EventDrilldownItem, 0, len(response.Hits.Hits))
	for _, hit := range response.Hits.Hits {
		row := elasticsearchSourceToStringMap(hit.Source)
		rows = append(rows, row)
		items = append(
			items,
			decodeEventDrilldownFields(row, query.RevealSession),
		)
	}
	generatedThrough, lagSeconds := rawRecordWaterline(rows, s.now().UTC())
	freshness := "no_samples"
	if len(items) > 0 {
		freshness = "near_realtime"
	}
	return application.EventDrilldown{
		TotalCount:       response.Hits.Total.Value,
		Items:            items,
		SourceKind:       "raw_records",
		Freshness:        freshness,
		GeneratedThrough: generatedThrough,
		LagSeconds:       lagSeconds,
		ActualFrom:       query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:         query.To.UTC().Format(time.RFC3339Nano),
	}, nil
}

func (s *ElasticsearchEventLogStore) GetRuntimeLogDrilldown(
	ctx context.Context,
	query application.RuntimeLogDrilldownQuery,
) (application.RuntimeLogDrilldown, error) {
	filters := []any{elasticsearchRangeFilter("occurredAt", query.From, query.To)}
	for field, value := range map[string]string{
		"signal":             query.Signal,
		"severity":           query.Severity,
		"errorCode":          query.ErrorCode,
		"fingerprint":        query.Fingerprint,
		"resourceSourceType": query.SourceType,
		"resourceService":    query.Service,
		"resourceAppVersion": query.AppVersion,
		"actorHash":          query.ActorHash,
	} {
		if value != "" {
			filters = append(
				filters,
				map[string]any{"term": map[string]any{field: value}},
			)
		}
	}
	boolQuery := map[string]any{"filter": filters}
	if query.MessageContains != "" {
		boolQuery["must"] = []any{
			map[string]any{
				"match_phrase": map[string]any{
					"message": query.MessageContains,
				},
			},
		}
	}
	var response struct {
		Hits elasticsearchHits `json:"hits"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RuntimeLogIndex), map[string]any{
		"size":             query.Limit,
		"track_total_hits": true,
		"query":            map[string]any{"bool": boolQuery},
		"sort":             []any{map[string]any{"occurredAt": "desc"}},
	}, &response); err != nil {
		return application.RuntimeLogDrilldown{}, fmt.Errorf(
			"query Elasticsearch runtime raw records: %w",
			err,
		)
	}
	rows := make([]map[string]string, 0, len(response.Hits.Hits))
	items := make([]application.RuntimeLogDrilldownItem, 0, len(response.Hits.Hits))
	for _, hit := range response.Hits.Hits {
		row := elasticsearchSourceToStringMap(hit.Source)
		rows = append(rows, row)
		items = append(
			items,
			decodeRuntimeLogDrilldownFields(row, query.RevealCorrelation),
		)
	}
	generatedThrough, lagSeconds := rawRecordWaterline(rows, s.now().UTC())
	freshness := "no_samples"
	if len(items) > 0 {
		freshness = "near_realtime"
	}
	return application.RuntimeLogDrilldown{
		TotalCount:       response.Hits.Total.Value,
		Items:            items,
		SourceKind:       "raw_records",
		Freshness:        freshness,
		GeneratedThrough: generatedThrough,
		LagSeconds:       lagSeconds,
		ActualFrom:       query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:         query.To.UTC().Format(time.RFC3339Nano),
	}, nil
}

func (s *ElasticsearchEventLogStore) GetPageExperienceStats(
	ctx context.Context,
	query application.PageExperienceQuery,
) ([]application.PageExperienceStat, error) {
	var response struct {
		Aggregations struct {
			Pages struct {
				Buckets []struct {
					Key   string `json:"key"`
					Opens struct {
						DocCount int64 `json:"doc_count"`
						Ready    struct {
							Value *float64 `json:"value"`
						} `json:"avg_ready"`
						ReadySamples struct {
							DocCount int64 `json:"doc_count"`
						} `json:"ready_samples"`
					} `json:"opens"`
					Stays struct {
						DocCount int64 `json:"doc_count"`
						Average  struct {
							Value *float64 `json:"value"`
						} `json:"avg_stay"`
					} `json:"stays"`
					RuntimeErrors struct {
						DocCount int64 `json:"doc_count"`
					} `json:"runtime_errors"`
				} `json:"buckets"`
			} `json:"pages"`
		} `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
		"size": 0,
		"query": map[string]any{
			"bool": map[string]any{
				"filter": []any{
					elasticsearchRangeFilter("occurredAt", query.From, query.To),
					map[string]any{"exists": map[string]any{"field": "pageName"}},
				},
			},
		},
		"aggs": map[string]any{
			"pages": map[string]any{
				"terms": map[string]any{"field": "pageName", "size": 500},
				"aggs": map[string]any{
					"opens": map[string]any{
						"filter": map[string]any{"term": map[string]any{"eventType": "page_open"}},
						"aggs": map[string]any{
							"avg_ready": map[string]any{"avg": map[string]any{"field": "readyMs"}},
							"ready_samples": map[string]any{
								"filter": map[string]any{"exists": map[string]any{"field": "readyMs"}},
							},
						},
					},
					"stays": map[string]any{
						"filter": map[string]any{"term": map[string]any{"eventType": "page_return"}},
						"aggs": map[string]any{
							"avg_stay": map[string]any{"avg": map[string]any{"field": "durationMs"}},
						},
					},
					"runtime_errors": map[string]any{
						"filter": map[string]any{"term": map[string]any{"eventType": "runtime_exception"}},
					},
				},
			},
		},
	}, &response); err != nil {
		return nil, fmt.Errorf(
			"query Elasticsearch page experience: %w",
			err,
		)
	}
	items := make([]application.PageExperienceStat, 0, len(response.Aggregations.Pages.Buckets))
	for _, bucket := range response.Aggregations.Pages.Buckets {
		item := application.PageExperienceStat{
			PageName:      bucket.Key,
			Opens:         bucket.Opens.DocCount,
			ReadySamples:  bucket.Opens.ReadySamples.DocCount,
			StaySamples:   bucket.Stays.DocCount,
			RuntimeErrors: bucket.RuntimeErrors.DocCount,
		}
		if bucket.Opens.Ready.Value != nil {
			item.AvgReadyMs = *bucket.Opens.Ready.Value
		}
		if bucket.Stays.Average.Value != nil {
			item.AvgStayMs = *bucket.Stays.Average.Value
		}
		items = append(items, item)
	}
	return items, nil
}

// GetEventValueStats 从 raw 权威事实读取数值字段统计（与 RTC QoE 相同的
// 原始样本口径）：percentile 用 ES percentiles 聚合，sum_ratio 用 sum 聚合；
// 无样本返回零计数，调用方显式 unavailable。
func (s *ElasticsearchEventLogStore) GetEventValueStats(
	ctx context.Context,
	query application.EventValueStatsQuery,
) (application.EventValueStats, error) {
	filters := []any{
		elasticsearchRangeFilter("occurredAt", query.From, query.To),
		map[string]any{"term": map[string]any{"eventType": query.EventType}},
	}
	if query.Result != "" {
		filters = append(filters, map[string]any{
			"term": map[string]any{"result": query.Result},
		})
	}
	countField := query.ValueField
	if countField == "" {
		countField = query.DenominatorField
	}
	aggregations := map[string]any{
		"samples": map[string]any{
			"value_count": map[string]any{"field": countField},
		},
	}
	if query.ValueField != "" {
		aggregations["p95"] = map[string]any{
			"percentiles": map[string]any{
				"field":    query.ValueField,
				"percents": []float64{95},
			},
		}
	}
	if query.NumeratorField != "" {
		aggregations["numeratorSum"] = map[string]any{
			"sum": map[string]any{"field": query.NumeratorField},
		}
	}
	if query.DenominatorField != "" {
		aggregations["denominatorSum"] = map[string]any{
			"sum": map[string]any{"field": query.DenominatorField},
		}
	}
	var response struct {
		Aggregations struct {
			Samples struct {
				Value float64 `json:"value"`
			} `json:"samples"`
			P95 struct {
				Values map[string]*float64 `json:"values"`
			} `json:"p95"`
			NumeratorSum struct {
				Value float64 `json:"value"`
			} `json:"numeratorSum"`
			DenominatorSum struct {
				Value float64 `json:"value"`
			} `json:"denominatorSum"`
		} `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
		"size":  0,
		"query": map[string]any{"bool": map[string]any{"filter": filters}},
		"aggs":  aggregations,
	}, &response); err != nil {
		return application.EventValueStats{}, fmt.Errorf(
			"query Elasticsearch event value stats: %w", err,
		)
	}
	stats := application.EventValueStats{
		SampleCount:    int64(response.Aggregations.Samples.Value),
		NumeratorSum:   response.Aggregations.NumeratorSum.Value,
		DenominatorSum: response.Aggregations.DenominatorSum.Value,
	}
	if p95 := response.Aggregations.P95.Values["95.0"]; p95 != nil {
		stats.P95 = *p95
	}
	return stats, nil
}

// ListDistinctSessionsByEvent 按事件类型列举窗口内 distinct sessionId
// （跨轨漏斗产品轨段的 actor 去重输入）。
func (s *ElasticsearchEventLogStore) ListDistinctSessionsByEvent(
	ctx context.Context,
	eventType string,
	from time.Time,
	to time.Time,
	limit int,
) ([]string, error) {
	if limit <= 0 {
		return nil, fmt.Errorf("Elasticsearch distinct session limit must be positive")
	}
	sessions := make([]string, 0, min(limit, 1000))
	var after map[string]any
	for len(sessions) < limit {
		pageSize := min(1000, limit-len(sessions))
		composite := map[string]any{
			"size": pageSize,
			"sources": []any{
				map[string]any{
					"sessionId": map[string]any{
						"terms": map[string]any{"field": "sessionId"},
					},
				},
			},
		}
		if len(after) > 0 {
			composite["after"] = after
		}
		var response struct {
			Aggregations struct {
				Sessions struct {
					Buckets []struct {
						Key map[string]any `json:"key"`
					} `json:"buckets"`
					AfterKey map[string]any `json:"after_key"`
				} `json:"sessions"`
			} `json:"aggregations"`
		}
		if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
			"size": 0,
			"query": map[string]any{
				"bool": map[string]any{
					"filter": []any{
						elasticsearchRangeFilter("occurredAt", from, to),
						map[string]any{"term": map[string]any{"eventType": eventType}},
						map[string]any{"exists": map[string]any{"field": "sessionId"}},
					},
				},
			},
			"aggs": map[string]any{
				"sessions": map[string]any{"composite": composite},
			},
		}, &response); err != nil {
			return nil, fmt.Errorf(
				"query Elasticsearch distinct sessions by event: %w", err,
			)
		}
		for _, bucket := range response.Aggregations.Sessions.Buckets {
			sessionID := fmt.Sprint(bucket.Key["sessionId"])
			if sessionID != "" {
				sessions = append(sessions, sessionID)
			}
		}
		if len(response.Aggregations.Sessions.Buckets) < pageSize ||
			len(response.Aggregations.Sessions.AfterKey) == 0 {
			return sessions, nil
		}
		after = response.Aggregations.Sessions.AfterKey
	}
	return sessions, nil
}

func (s *ElasticsearchEventLogStore) ListDistinctSessions(
	ctx context.Context,
	from time.Time,
	to time.Time,
	limit int,
) ([]string, int64, error) {
	if limit <= 0 {
		return nil, 0, fmt.Errorf("Elasticsearch distinct session limit must be positive")
	}
	sessions := make([]string, 0, min(limit, 1000))
	var after map[string]any
	// PV 口径 = page_open 事件数（页面浏览量），不是窗口内全事件条数；
	// 全事件数会把行为/诊断类事件也计入，系统性高估 PV。
	var pageViews int64
	for len(sessions) < limit {
		pageSize := min(1000, limit-len(sessions))
		composite := map[string]any{
			"size": pageSize,
			"sources": []any{
				map[string]any{
					"sessionId": map[string]any{
						"terms": map[string]any{"field": "sessionId"},
					},
				},
			},
		}
		if len(after) > 0 {
			composite["after"] = after
		}
		var response struct {
			Hits         elasticsearchHits `json:"hits"`
			Aggregations struct {
				Sessions struct {
					Buckets []struct {
						Key map[string]any `json:"key"`
					} `json:"buckets"`
					AfterKey map[string]any `json:"after_key"`
				} `json:"sessions"`
				PageViews struct {
					DocCount int64 `json:"doc_count"`
				} `json:"pageViews"`
			} `json:"aggregations"`
		}
		if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
			"size":             0,
			"track_total_hits": true,
			"query": map[string]any{
				"bool": map[string]any{
					"filter": []any{
						elasticsearchRangeFilter("occurredAt", from, to),
						map[string]any{"exists": map[string]any{"field": "sessionId"}},
					},
				},
			},
			"aggs": map[string]any{
				"sessions": map[string]any{"composite": composite},
				"pageViews": map[string]any{
					"filter": map[string]any{
						"term": map[string]any{"eventType": "page_open"},
					},
				},
			},
		}, &response); err != nil {
			return nil, 0, fmt.Errorf(
				"query Elasticsearch distinct sessions: %w",
				err,
			)
		}
		pageViews = response.Aggregations.PageViews.DocCount
		for _, bucket := range response.Aggregations.Sessions.Buckets {
			sessionID := fmt.Sprint(bucket.Key["sessionId"])
			if sessionID != "" {
				sessions = append(sessions, sessionID)
			}
		}
		if len(response.Aggregations.Sessions.Buckets) < pageSize ||
			len(response.Aggregations.Sessions.AfterKey) == 0 {
			return sessions, pageViews, nil
		}
		after = response.Aggregations.Sessions.AfterKey
	}
	hasMore, err := s.hasDistinctSessionAfter(ctx, from, to, after)
	if err != nil {
		return nil, 0, err
	}
	if hasMore {
		return nil, 0, fmt.Errorf(
			"Elasticsearch distinct session count exceeds limit=%d",
			limit,
		)
	}
	return sessions, pageViews, nil
}

func (s *ElasticsearchEventLogStore) hasDistinctSessionAfter(
	ctx context.Context,
	from time.Time,
	to time.Time,
	after map[string]any,
) (bool, error) {
	if len(after) == 0 {
		return false, nil
	}
	var response struct {
		Aggregations struct {
			Sessions struct {
				Buckets []json.RawMessage `json:"buckets"`
			} `json:"sessions"`
		} `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
		"size": 0,
		"query": map[string]any{
			"bool": map[string]any{
				"filter": []any{
					elasticsearchRangeFilter("occurredAt", from, to),
					map[string]any{"exists": map[string]any{"field": "sessionId"}},
				},
			},
		},
		"aggs": map[string]any{
			"sessions": map[string]any{
				"composite": map[string]any{
					"size":  1,
					"after": after,
					"sources": []any{
						map[string]any{
							"sessionId": map[string]any{
								"terms": map[string]any{"field": "sessionId"},
							},
						},
					},
				},
			},
		},
	}, &response); err != nil {
		return false, fmt.Errorf(
			"probe Elasticsearch distinct session limit: %w",
			err,
		)
	}
	return len(response.Aggregations.Sessions.Buckets) > 0, nil
}

func (s *ElasticsearchEventLogStore) ReadRtcMediaQoeSummary(
	ctx context.Context,
	query application.RtcMediaQoeSummaryQuery,
) (application.RtcMediaQoeSummarySlice, error) {
	metrics := elasticsearchRtcMetricsAggregations()
	aggregations := map[string]any{
		"hourly": map[string]any{
			"date_histogram": map[string]any{
				"field":          "occurredAt",
				"fixed_interval": "1h",
				"min_doc_count":  1,
			},
			"aggs": metrics,
		},
	}
	for key, value := range metrics {
		aggregations[key] = value
	}
	var response struct {
		Hits         elasticsearchHits            `json:"hits"`
		Aggregations elasticsearchRtcAggregations `json:"aggregations"`
	}
	if err := s.search(ctx, elasticsearchIndexPattern(s.config.RawIndex), map[string]any{
		"size":             0,
		"track_total_hits": true,
		"query": map[string]any{
			"bool": map[string]any{
				"filter": []any{
					map[string]any{"term": map[string]any{"eventType": "rtc_media_qoe"}},
					map[string]any{"exists": map[string]any{"field": "result"}},
					elasticsearchRangeFilter("occurredAt", query.From, query.To),
				},
				"must_not": []any{
					map[string]any{"term": map[string]any{"result": "abandoned"}},
				},
			},
		},
		"aggs": aggregations,
	}, &response); err != nil {
		return application.RtcMediaQoeSummarySlice{}, fmt.Errorf(
			"query Elasticsearch rtc_media_qoe raw records: %w",
			err,
		)
	}
	hourly := make(
		[]application.RtcMediaQoeAggregate,
		0,
		len(response.Aggregations.Hourly.Buckets),
	)
	for _, bucket := range response.Aggregations.Hourly.Buckets {
		item, err := elasticsearchRtcAggregate(
			bucket.DocCount,
			bucket.Connected,
			bucket.Reconnect,
			bucket.GeneratedThrough,
		)
		if err != nil {
			return application.RtcMediaQoeSummarySlice{}, err
		}
		item.BucketStart = time.UnixMilli(bucket.Key).UTC()
		hourly = append(hourly, item)
	}
	total, err := elasticsearchRtcAggregate(
		response.Hits.Total.Value,
		response.Aggregations.Connected,
		response.Aggregations.Reconnect,
		response.Aggregations.GeneratedThrough,
	)
	if err != nil {
		return application.RtcMediaQoeSummarySlice{}, err
	}
	return application.BuildRtcMediaQoeSummary(
		query,
		hourly,
		total,
		"raw_records",
	), nil
}

type elasticsearchRtcConnected struct {
	DocCount   int64 `json:"doc_count"`
	ConnectP95 struct {
		Values map[string]*float64 `json:"values"`
	} `json:"connect_p95"`
	ConnectionLost struct {
		DocCount int64 `json:"doc_count"`
	} `json:"connection_lost"`
}

type elasticsearchRtcSum struct {
	Value float64 `json:"value"`
}

type elasticsearchRtcAggregations struct {
	Connected        elasticsearchRtcConnected `json:"connected"`
	Reconnect        elasticsearchRtcSum       `json:"reconnect"`
	GeneratedThrough elasticsearchMaxMetric    `json:"generated_through"`
	Hourly           struct {
		Buckets []struct {
			Key              int64                     `json:"key"`
			DocCount         int64                     `json:"doc_count"`
			Connected        elasticsearchRtcConnected `json:"connected"`
			Reconnect        elasticsearchRtcSum       `json:"reconnect"`
			GeneratedThrough elasticsearchMaxMetric    `json:"generated_through"`
		} `json:"buckets"`
	} `json:"hourly"`
}

func elasticsearchRtcMetricsAggregations() map[string]any {
	return map[string]any{
		"connected": map[string]any{
			"filter": map[string]any{"term": map[string]any{"mediaConnected": true}},
			"aggs": map[string]any{
				"connect_p95": map[string]any{
					"percentiles": map[string]any{
						"field":    "connectTimeMs",
						"percents": []float64{95},
					},
				},
				"connection_lost": map[string]any{
					"filter": map[string]any{"term": map[string]any{"result": "connection_lost"}},
				},
			},
		},
		"reconnect": map[string]any{"sum": map[string]any{"field": "reconnectCount"}},
		"generated_through": map[string]any{
			"max": map[string]any{
				"field":  "ingestedAt",
				"format": "strict_date_optional_time_nanos",
			},
		},
	}
}

func elasticsearchRtcAggregate(
	effective int64,
	connected elasticsearchRtcConnected,
	reconnect elasticsearchRtcSum,
	generated elasticsearchMaxMetric,
) (application.RtcMediaQoeAggregate, error) {
	if connected.DocCount > effective ||
		connected.ConnectionLost.DocCount > connected.DocCount {
		return application.RtcMediaQoeAggregate{}, fmt.Errorf(
			"invalid Elasticsearch rtc_media_qoe counts effective=%d connected=%d lost=%d",
			effective,
			connected.DocCount,
			connected.ConnectionLost.DocCount,
		)
	}
	out := application.RtcMediaQoeAggregate{
		EffectiveSampleCount: effective,
		MediaConnectedCount:  connected.DocCount,
		ConnectionLostCount:  connected.ConnectionLost.DocCount,
		ReconnectCount:       int64(math.Round(reconnect.Value)),
	}
	if value := connected.ConnectP95.Values["95.0"]; value != nil &&
		!math.IsNaN(*value) {
		out.ConnectP95MS = value
	}
	if generated.Value != nil && generated.ValueAsString != "" {
		value, err := time.Parse(time.RFC3339Nano, generated.ValueAsString)
		if err != nil {
			return application.RtcMediaQoeAggregate{}, fmt.Errorf(
				"decode Elasticsearch generatedThrough: %w",
				err,
			)
		}
		value = value.UTC()
		out.GeneratedThrough = &value
	}
	return out, nil
}

func elasticsearchRangeFilter(field string, from, to time.Time) map[string]any {
	return map[string]any{
		"range": map[string]any{
			field: map[string]any{
				"gte": from.UTC().Format(time.RFC3339Nano),
				"lt":  to.UTC().Format(time.RFC3339Nano),
			},
		},
	}
}

func elasticsearchMetricValue(raw json.RawMessage) float64 {
	var metric struct {
		Value float64 `json:"value"`
	}
	_ = json.Unmarshal(raw, &metric)
	return metric.Value
}

func elasticsearchDimensionCounts(
	raw json.RawMessage,
) (map[string]int, error) {
	var terms struct {
		Buckets []struct {
			Key           any `json:"key"`
			WeightedCount struct {
				Value float64 `json:"value"`
			} `json:"weighted_count"`
		} `json:"buckets"`
	}
	if err := json.Unmarshal(raw, &terms); err != nil {
		return nil, err
	}
	counts := map[string]int{}
	for _, bucket := range terms.Buckets {
		key := fmt.Sprint(bucket.Key)
		count := int(math.Round(bucket.WeightedCount.Value))
		if key != "" && count > 0 {
			counts[key] = count
		}
	}
	return counts, nil
}

func applyElasticsearchWaterline(
	freshness *string,
	generatedThrough *string,
	lagSeconds *int64,
	raw json.RawMessage,
	now time.Time,
	nonEmptyFreshness string,
) {
	var metric elasticsearchMaxMetric
	if err := json.Unmarshal(raw, &metric); err != nil ||
		metric.Value == nil ||
		metric.ValueAsString == "" {
		return
	}
	*generatedThrough = metric.ValueAsString
	*freshness = nonEmptyFreshness
	if timestamp, err := time.Parse(time.RFC3339Nano, metric.ValueAsString); err == nil {
		lag := int64(now.Sub(timestamp.UTC()).Seconds())
		if lag < 0 {
			lag = 0
		}
		*lagSeconds = lag
	}
}

func elasticsearchSourceToStringMap(source map[string]any) map[string]string {
	out := make(map[string]string, len(source))
	for key, value := range source {
		switch typed := value.(type) {
		case nil:
		case string:
			out[key] = typed
		case bool:
			out[key] = strconv.FormatBool(typed)
		case float64:
			out[key] = strconv.FormatFloat(typed, 'f', -1, 64)
		case json.Number:
			out[key] = typed.String()
		default:
			encoded, err := json.Marshal(typed)
			if err == nil {
				out[key] = string(encoded)
			}
		}
	}
	return out
}
