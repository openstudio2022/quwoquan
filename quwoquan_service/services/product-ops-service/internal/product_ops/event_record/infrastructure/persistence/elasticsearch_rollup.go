package persistence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strconv"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

// buildEventRollupDocuments / buildRuntimeLogRollupDocuments 是
// rollup_executor 的薄包装：分别对 raw_records / runtime_records source
// 执行 RollupCatalog 中声明的全部 rowKind。
func buildEventRollupDocuments(
	index string,
	batchKey string,
	records []application.EventRecord,
) ([]elasticsearchBulkDocument, error) {
	rows := make([]rollupSourceRow, 0, len(records))
	for _, record := range records {
		rows = append(rows, rollupSourceRow{
			fields:     eventRecordFields(record),
			ingestedAt: record.IngestedAt,
		})
	}
	return buildContractRollupDocuments(index, batchKey, "raw_records", "event", rows)
}

func buildRuntimeLogRollupDocuments(
	index string,
	batchKey string,
	records []application.RuntimeLogRecord,
) ([]elasticsearchBulkDocument, error) {
	rows := make([]rollupSourceRow, 0, len(records))
	for _, record := range records {
		rows = append(rows, rollupSourceRow{
			fields:     record.Fields,
			ingestedAt: record.IngestedAt,
		})
	}
	return buildContractRollupDocuments(index, batchKey, "runtime_records", "runtime", rows)
}

func rollupDocumentID(
	prefix string,
	batchKey string,
	source map[string]any,
	fields []string,
) string {
	group := make(map[string]any, len(fields))
	for _, field := range fields {
		group[field] = source[field]
	}
	canonical, _ := json.Marshal(group)
	digest := sha256.Sum256(canonical)
	return prefix + ":" + batchKey + ":" + hex.EncodeToString(digest[:8])
}

// rollupRowsFromElasticsearchDocuments 把 raw 文档转成聚合执行器输入行。
// 必须保留全部 wire 字段（含事件扩展），否则重建的聚合行身份会漂移。
func rollupRowsFromElasticsearchDocuments(
	documents []map[string]any,
) ([]rollupSourceRow, error) {
	rows := make([]rollupSourceRow, 0, len(documents))
	for _, document := range documents {
		fields := elasticsearchSourceToStringMap(document)
		ingestedAt, err := time.Parse(time.RFC3339Nano, fields["ingestedAt"])
		if err != nil {
			return nil, fmt.Errorf(
				"decode Elasticsearch event ingestedAt: %w",
				err,
			)
		}
		rows = append(rows, rollupSourceRow{
			fields:     fields,
			ingestedAt: ingestedAt.UTC(),
		})
	}
	return rows, nil
}

func runtimeLogRecordsFromElasticsearchDocuments(
	documents []map[string]any,
) ([]application.RuntimeLogRecord, error) {
	records := make([]application.RuntimeLogRecord, 0, len(documents))
	for _, document := range documents {
		fields := elasticsearchSourceToStringMap(document)
		batchIndex, err := strconv.Atoi(fields["_batchIndex"])
		if err != nil {
			return nil, fmt.Errorf(
				"decode Elasticsearch runtime batch index: %w",
				err,
			)
		}
		ingestedAt, err := time.Parse(time.RFC3339Nano, fields["ingestedAt"])
		if err != nil {
			return nil, fmt.Errorf(
				"decode Elasticsearch runtime ingestedAt: %w",
				err,
			)
		}
		records = append(records, application.RuntimeLogRecord{
			Fields:     fields,
			BatchKey:   fields["_batchKey"],
			BatchIndex: batchIndex,
			IngestedAt: ingestedAt.UTC(),
		})
	}
	return records, nil
}
