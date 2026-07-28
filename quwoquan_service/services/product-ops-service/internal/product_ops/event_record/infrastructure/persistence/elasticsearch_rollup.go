package persistence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strconv"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

func buildEventRollupDocuments(
	index string,
	batchKey string,
	records []application.EventRecord,
) ([]elasticsearchBulkDocument, error) {
	type rollup struct {
		source   map[string]any
		sessions map[string]struct{}
	}
	grouped := map[string]*rollup{}
	for _, record := range records {
		fields := eventRecordFields(record)
		source, err := eventRollupGroupSource(fields)
		if err != nil {
			return nil, err
		}
		groupKeyBytes, _ := json.Marshal(source)
		groupKey := string(groupKeyBytes)
		item := grouped[groupKey]
		if item == nil {
			source["count"] = int64(0)
			source["generatedThrough"] = record.IngestedAt.UTC().Format(time.RFC3339Nano)
			item = &rollup{source: source, sessions: map[string]struct{}{}}
			grouped[groupKey] = item
		}
		item.source["count"] = item.source["count"].(int64) + 1
		generatedThrough := record.IngestedAt.UTC().Format(time.RFC3339Nano)
		if generatedThrough > item.source["generatedThrough"].(string) {
			item.source["generatedThrough"] = generatedThrough
		}
		if record.SessionID != "" {
			sessionDigest := sha256.Sum256([]byte(record.SessionID))
			item.sessions[hex.EncodeToString(sessionDigest[:])] = struct{}{}
		}
	}
	keys := make([]string, 0, len(grouped))
	for key := range grouped {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	documents := make([]elasticsearchBulkDocument, 0, len(keys))
	for _, key := range keys {
		item := grouped[key]
		sessions := make([]string, 0, len(item.sessions))
		for sessionID := range item.sessions {
			sessions = append(sessions, sessionID)
		}
		sort.Strings(sessions)
		item.source["sessionHashes"] = sessions
		targetIndex, err := dailyElasticsearchIndex(
			index,
			item.source["bucketStart"].(string),
		)
		if err != nil {
			return nil, fmt.Errorf(
				"resolve Elasticsearch event aggregate index: %w",
				err,
			)
		}
		documents = append(documents, elasticsearchBulkDocument{
			Index:  targetIndex,
			ID:     eventRollupDocumentID(batchKey, item.source),
			Source: item.source,
		})
	}
	return documents, nil
}

func buildRuntimeLogRollupDocuments(
	index string,
	batchKey string,
	records []application.RuntimeLogRecord,
) ([]elasticsearchBulkDocument, error) {
	grouped := map[string]map[string]any{}
	for _, record := range records {
		source, err := runtimeLogRollupGroupSource(record.Fields)
		if err != nil {
			return nil, err
		}
		groupKeyBytes, _ := json.Marshal(source)
		groupKey := string(groupKeyBytes)
		item := grouped[groupKey]
		if item == nil {
			source["count"] = int64(0)
			source["generatedThrough"] = record.IngestedAt.UTC().Format(time.RFC3339Nano)
			item = source
			grouped[groupKey] = item
		}
		item["count"] = item["count"].(int64) + 1
		generatedThrough := record.IngestedAt.UTC().Format(time.RFC3339Nano)
		if generatedThrough > item["generatedThrough"].(string) {
			item["generatedThrough"] = generatedThrough
		}
	}
	keys := make([]string, 0, len(grouped))
	for key := range grouped {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	documents := make([]elasticsearchBulkDocument, 0, len(keys))
	for _, key := range keys {
		source := grouped[key]
		targetIndex, err := dailyElasticsearchIndex(
			index,
			source["bucketStart"].(string),
		)
		if err != nil {
			return nil, fmt.Errorf(
				"resolve Elasticsearch runtime aggregate index: %w",
				err,
			)
		}
		documents = append(documents, elasticsearchBulkDocument{
			Index:  targetIndex,
			ID:     runtimeLogRollupDocumentID(batchKey, source),
			Source: source,
		})
	}
	return documents, nil
}

func eventRollupGroupSource(fields map[string]string) (map[string]any, error) {
	occurredAt, err := time.Parse(time.RFC3339Nano, fields["occurredAt"])
	if err != nil {
		return nil, fmt.Errorf(
			"parse event occurredAt for Elasticsearch rollup: %w",
			err,
		)
	}
	return map[string]any{
		"rowKind":            "event_dimensions",
		"bucketStart":        occurredAt.UTC().Truncate(time.Hour).Format(time.RFC3339Nano),
		"logType":            fields["logType"],
		"eventType":          fields["eventType"],
		"pageName":           fields["pageName"],
		"appVersion":         fields["appVersion"],
		"networkClass":       fields["networkClass"],
		"deviceManufacturer": fields["deviceManufacturer"],
		"deviceModel":        fields["deviceModel"],
		"journey":            fields["journey"],
		"action":             fields["action"],
		"result":             fields["result"],
		"errorCode":          fields["errorCode"],
	}, nil
}

func runtimeLogRollupGroupSource(
	fields map[string]string,
) (map[string]any, error) {
	occurredAt, err := time.Parse(time.RFC3339Nano, fields["occurredAt"])
	if err != nil {
		return nil, fmt.Errorf(
			"parse runtime log occurredAt for Elasticsearch rollup: %w",
			err,
		)
	}
	return map[string]any{
		"rowKind":            "runtime_diagnostics",
		"bucketStart":        occurredAt.UTC().Truncate(time.Hour).Format(time.RFC3339Nano),
		"logKind":            fields["logKind"],
		"severity":           fields["severity"],
		"signal":             fields["signal"],
		"errorCode":          fields["errorCode"],
		"fingerprint":        fields["fingerprint"],
		"resourceSourceType": fields["resourceSourceType"],
		"resourceService":    fields["resourceService"],
		"resourceAppVersion": fields["resourceAppVersion"],
	}, nil
}

func eventRollupDocumentID(batchKey string, source map[string]any) string {
	return rollupDocumentID(
		"event",
		batchKey,
		source,
		[]string{
			"rowKind",
			"bucketStart",
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
		},
	)
}

func runtimeLogRollupDocumentID(batchKey string, source map[string]any) string {
	return rollupDocumentID(
		"runtime",
		batchKey,
		source,
		[]string{
			"rowKind",
			"bucketStart",
			"logKind",
			"severity",
			"signal",
			"errorCode",
			"fingerprint",
			"resourceSourceType",
			"resourceService",
			"resourceAppVersion",
		},
	)
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

func eventRecordsFromElasticsearchDocuments(
	documents []map[string]any,
) ([]application.EventRecord, error) {
	records := make([]application.EventRecord, 0, len(documents))
	for _, document := range documents {
		fields := elasticsearchSourceToStringMap(document)
		batchIndex, err := strconv.Atoi(fields["_batchIndex"])
		if err != nil {
			return nil, fmt.Errorf(
				"decode Elasticsearch event batch index: %w",
				err,
			)
		}
		ingestedAt, err := time.Parse(time.RFC3339Nano, fields["ingestedAt"])
		if err != nil {
			return nil, fmt.Errorf(
				"decode Elasticsearch event ingestedAt: %w",
				err,
			)
		}
		records = append(records, application.EventRecord{
			EventRecordInput: application.EventRecordInput{
				LogType:            fields["logType"],
				EventType:          fields["eventType"],
				SessionID:          fields["sessionId"],
				PageName:           fields["pageName"],
				OccurredAt:         fields["occurredAt"],
				DeviceManufacturer: fields["deviceManufacturer"],
				DeviceModel:        fields["deviceModel"],
				AppVersion:         fields["appVersion"],
				NetworkClass:       fields["networkClass"],
				DevicePlatform:     fields["devicePlatform"],
				Journey:            optionalString(fields["journey"]),
				Action:             optionalString(fields["action"]),
				Result:             optionalString(fields["result"]),
				ErrorCode:          optionalString(fields["errorCode"]),
			},
			BatchKey:   fields["_batchKey"],
			BatchIndex: batchIndex,
			IngestedAt: ingestedAt.UTC(),
		})
	}
	return records, nil
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

func optionalString(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}
