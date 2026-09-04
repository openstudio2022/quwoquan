package persistence

func elasticsearchIndexSettings(policy string) map[string]any {
	return map[string]any{
		"number_of_shards":     1,
		"number_of_replicas":   0,
		"refresh_interval":     "1s",
		"index.lifecycle.name": policy,
	}
}

func elasticsearchDynamicTemplates() []any {
	return []any{
		map[string]any{
			"strings_as_keywords": map[string]any{
				"match_mapping_type": "string",
				"mapping": map[string]any{
					"type":         "keyword",
					"ignore_above": 4096,
				},
			},
		},
	}
}

// ElasticsearchRawNumericExtensionFields 是 raw 索引显式声明为 long 的
// 扩展字段清单，也是黄金指标 raw 统计（percentile_p95 / sum_ratio）的
// mapping 合约面：catalog 引用的 value 字段一旦缺席，会落入 keyword
// 动态模板并让数值聚合 400。
func ElasticsearchRawNumericExtensionFields() []string {
	return []string{
		"durationMs",
		"candidatesTried",
		"httpStatus",
		"tClickToFirstFrameMs",
		"tFirstFrameToShellMs",
		"tShellToContentMs",
		"tClickToContentMs",
		"readyMs",
		"ttffMs",
		"rebufferCount",
		"rebufferMs",
		"effectivePlaybackMs",
		"seekCount",
		"seekFailureCount",
		"seekCommandMaxMs",
		"seekSettleMaxMs",
		"droppedFrames",
		"processedVideoFrames",
		"audioUnderrunCount",
		"declaredDurationMs",
		"observedDurationMs",
		"connectTimeMs",
		"reconnectCount",
		// app_frame_jank_outcome 的全部数值扩展：jankyFrames/sampledFrames 是
		// app_jank_frame_rate 黄金指标 sum_ratio 的分子分母。
		"sampledFrames",
		"jankyFrames",
		"worstFrameMs",
		"worstBuildFrameMs",
		"worstRasterFrameMs",
		"jankThresholdMs",
	}
}

func elasticsearchRawIndexDefinition() map[string]any {
	properties := map[string]any{
		"occurredAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
		"ingestedAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
		"_batchIndex": map[string]any{"type": "integer"},
	}
	for _, field := range ElasticsearchRawNumericExtensionFields() {
		properties[field] = map[string]any{"type": "long", "coerce": true}
	}
	for _, field := range []string{
		"hasError",
		"decoderFallbackEnabled",
		"durationMismatch",
		"mediaConnected",
		"retryable",
	} {
		properties[field] = map[string]any{"type": "boolean"}
	}
	return map[string]any{
		"settings": elasticsearchIndexSettings(elasticsearchRawRetentionPolicy),
		"mappings": map[string]any{
			"dynamic":           true,
			"dynamic_templates": elasticsearchDynamicTemplates(),
			"properties":        properties,
			"_meta":             map[string]any{"retention_days": 3},
		},
	}
}

func elasticsearchStartupIndexDefinition() map[string]any {
	return map[string]any{
		"settings": elasticsearchIndexSettings(elasticsearchRawRetentionPolicy),
		"mappings": map[string]any{
			"dynamic":           true,
			"dynamic_templates": elasticsearchDynamicTemplates(),
			"properties": map[string]any{
				"occurredAt":        map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"ingestedAt":        map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"_batchIndex":       map[string]any{"type": "integer"},
				"sequence":          map[string]any{"type": "integer"},
				"phaseDurationMs":   map[string]any{"type": "long"},
				"elapsedMs":         map[string]any{"type": "long"},
				"recoverySurface":   map[string]any{"type": "keyword"},
				"recoveryLifecycle": map[string]any{"type": "keyword"},
				"recoveryMount":     map[string]any{"type": "keyword"},
				"recoveryPhase":     map[string]any{"type": "keyword"},
				"recoveryAction":    map[string]any{"type": "keyword"},
			},
			"_meta": map[string]any{"retention_days": 3},
		},
	}
}

func elasticsearchRuntimeIndexDefinition() map[string]any {
	return map[string]any{
		"settings": elasticsearchIndexSettings(elasticsearchRawRetentionPolicy),
		"mappings": map[string]any{
			"dynamic":           true,
			"dynamic_templates": elasticsearchDynamicTemplates(),
			"properties": map[string]any{
				"occurredAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"observedAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"ingestedAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"_batchIndex": map[string]any{"type": "integer"},
				"message":     map[string]any{"type": "text"},
			},
			"_meta": map[string]any{"retention_days": 3},
		},
	}
}

func elasticsearchAggregateIndexDefinition() map[string]any {
	return map[string]any{
		"settings": elasticsearchIndexSettings(elasticsearchAggregateRetentionPolicy),
		"mappings": map[string]any{
			"dynamic":           true,
			"dynamic_templates": elasticsearchDynamicTemplates(),
			"properties": map[string]any{
				"bucketStart":      map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"generatedThrough": map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"count":            map[string]any{"type": "long"},
				"sessionHashes":    map[string]any{"type": "keyword"},
			},
			"_meta": map[string]any{"retention_days": 90},
		},
	}
}
