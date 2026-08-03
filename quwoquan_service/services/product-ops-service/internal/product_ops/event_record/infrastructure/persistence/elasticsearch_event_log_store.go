package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

const maxElasticsearchResponseBytes = 16 << 20
const maxElasticsearchDailyIndexBaseBytes = 244

var elasticsearchIndexNamePattern = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]*$`)

const (
	elasticsearchRawRetentionPolicy       = "qwq-product-telemetry-raw-3d"
	elasticsearchAggregateRetentionPolicy = "qwq-product-telemetry-hourly-90d"
)

type ElasticsearchConfig struct {
	Endpoint               string
	APIKey                 string
	RawIndex               string
	StartupDiagnosticIndex string
	RuntimeLogIndex        string
	AggregateIndex         string
	Timeout                time.Duration
}

type ElasticsearchEventLogStore struct {
	config ElasticsearchConfig
	client *http.Client
	now    func() time.Time
}

var (
	_ application.ObservabilityLogSink              = (*ElasticsearchEventLogStore)(nil)
	_ application.RtcMediaQoeSummaryReader          = (*ElasticsearchEventLogStore)(nil)
	_ application.ActiveSessionLister               = (*ElasticsearchEventLogStore)(nil)
	_ application.IncompleteEventBatchRepairer      = (*ElasticsearchEventLogStore)(nil)
	_ application.IncompleteRuntimeLogBatchRepairer = (*ElasticsearchEventLogStore)(nil)
)

func NewElasticsearchEventLogStore(
	config ElasticsearchConfig,
) (*ElasticsearchEventLogStore, error) {
	config.Endpoint = strings.TrimRight(strings.TrimSpace(config.Endpoint), "/")
	config.APIKey = strings.TrimSpace(config.APIKey)
	if len(config.APIKey) > 4096 || strings.IndexFunc(config.APIKey, func(r rune) bool {
		return r < 0x21 || r > 0x7e
	}) >= 0 {
		return nil, fmt.Errorf("Elasticsearch API key is invalid")
	}
	if config.Timeout <= 0 || config.Timeout > 30*time.Second {
		return nil, fmt.Errorf("Elasticsearch timeout must be within 1ms..30s")
	}
	endpoint, err := url.Parse(config.Endpoint)
	if err != nil ||
		(endpoint.Scheme != "http" && endpoint.Scheme != "https") ||
		endpoint.Host == "" ||
		endpoint.User != nil ||
		endpoint.RawQuery != "" ||
		endpoint.Fragment != "" {
		return nil, fmt.Errorf("Elasticsearch endpoint is invalid")
	}
	for role, index := range map[string]string{
		"raw":                config.RawIndex,
		"startup_diagnostic": config.StartupDiagnosticIndex,
		"runtime_log":        config.RuntimeLogIndex,
		"aggregate":          config.AggregateIndex,
	} {
		if !elasticsearchIndexNamePattern.MatchString(index) ||
			strings.Contains(index, "..") ||
			len(index) > maxElasticsearchDailyIndexBaseBytes {
			return nil, fmt.Errorf("Elasticsearch %s index is invalid", role)
		}
	}
	return &ElasticsearchEventLogStore{
		config: config,
		client: &http.Client{Timeout: config.Timeout},
		now:    time.Now,
	}, nil
}

func (s *ElasticsearchEventLogStore) Ping(ctx context.Context) error {
	status, body, err := s.request(
		ctx,
		http.MethodGet,
		"/_cluster/health?wait_for_status=yellow&timeout=1s",
		nil,
		"application/json",
	)
	if err != nil {
		return err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return fmt.Errorf(
			"Elasticsearch health status=%d: %s",
			status,
			truncateElasticsearchBody(body),
		)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) EnsureIndices(ctx context.Context) error {
	for policy, minimumAge := range map[string]string{
		elasticsearchRawRetentionPolicy:       "3d",
		elasticsearchAggregateRetentionPolicy: "90d",
	} {
		if err := s.ensureLifecyclePolicy(ctx, policy, minimumAge); err != nil {
			return err
		}
	}
	for _, item := range []struct {
		name string
		body map[string]any
	}{
		{s.config.RawIndex, elasticsearchRawIndexDefinition()},
		{s.config.StartupDiagnosticIndex, elasticsearchStartupIndexDefinition()},
		{s.config.RuntimeLogIndex, elasticsearchRuntimeIndexDefinition()},
		{s.config.AggregateIndex, elasticsearchAggregateIndexDefinition()},
	} {
		if err := s.ensureIndexTemplate(ctx, item.name, item.body); err != nil {
			return err
		}
		index := dailyElasticsearchIndexForTime(item.name, s.now().UTC())
		if err := s.ensureIndex(ctx, index, item.body); err != nil {
			return err
		}
	}
	return nil
}

func (s *ElasticsearchEventLogStore) ensureLifecyclePolicy(
	ctx context.Context,
	policy string,
	minimumAge string,
) error {
	status, body, err := s.request(
		ctx,
		http.MethodPut,
		"/_ilm/policy/"+policy,
		map[string]any{
			"policy": map[string]any{
				"phases": map[string]any{
					"delete": map[string]any{
						"min_age": minimumAge,
						"actions": map[string]any{
							"delete": map[string]any{},
						},
					},
				},
			},
		},
		"application/json",
	)
	if err != nil {
		return fmt.Errorf("ensure Elasticsearch lifecycle policy %s: %w", policy, err)
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return fmt.Errorf(
			"ensure Elasticsearch lifecycle policy %s status=%d: %s",
			policy,
			status,
			truncateElasticsearchBody(body),
		)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) ensureIndexTemplate(
	ctx context.Context,
	indexBase string,
	definition map[string]any,
) error {
	status, body, err := s.request(
		ctx,
		http.MethodPut,
		"/_index_template/"+indexBase+"-template",
		map[string]any{
			"index_patterns": []string{elasticsearchIndexPattern(indexBase)},
			"priority":       500,
			"template":       definition,
		},
		"application/json",
	)
	if err != nil {
		return fmt.Errorf(
			"ensure Elasticsearch index template %s: %w",
			indexBase,
			err,
		)
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return fmt.Errorf(
			"ensure Elasticsearch index template %s status=%d: %s",
			indexBase,
			status,
			truncateElasticsearchBody(body),
		)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) ensureIndex(
	ctx context.Context,
	index string,
	definition map[string]any,
) error {
	status, body, err := s.request(
		ctx,
		http.MethodHead,
		"/"+index,
		nil,
		"application/json",
	)
	if err != nil {
		return fmt.Errorf("inspect Elasticsearch index %s: %w", index, err)
	}
	switch status {
	case http.StatusOK:
		settings, _ := definition["settings"].(map[string]any)
		dynamicSettings := make(map[string]any, len(settings))
		for key, value := range settings {
			if key != "number_of_shards" {
				dynamicSettings[key] = value
			}
		}
		status, body, err = s.request(
			ctx,
			http.MethodPut,
			"/"+index+"/_settings",
			dynamicSettings,
			"application/json",
		)
		if err != nil {
			return fmt.Errorf(
				"update Elasticsearch index %s settings: %w",
				index,
				err,
			)
		}
		if status < http.StatusOK || status >= http.StatusMultipleChoices {
			return fmt.Errorf(
				"update Elasticsearch index %s settings status=%d: %s",
				index,
				status,
				truncateElasticsearchBody(body),
			)
		}
		mappings, _ := definition["mappings"].(map[string]any)
		status, body, err = s.request(
			ctx,
			http.MethodPut,
			"/"+index+"/_mapping",
			mappings,
			"application/json",
		)
	case http.StatusNotFound:
		status, body, err = s.request(
			ctx,
			http.MethodPut,
			"/"+index,
			definition,
			"application/json",
		)
	default:
		return fmt.Errorf(
			"inspect Elasticsearch index %s status=%d: %s",
			index,
			status,
			truncateElasticsearchBody(body),
		)
	}
	if err != nil {
		return fmt.Errorf("ensure Elasticsearch index %s: %w", index, err)
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		if status == http.StatusBadRequest &&
			bytes.Contains(body, []byte("resource_already_exists_exception")) {
			return nil
		}
		return fmt.Errorf(
			"ensure Elasticsearch index %s status=%d: %s",
			index,
			status,
			truncateElasticsearchBody(body),
		)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) PutEventBatch(
	ctx context.Context,
	batchKey string,
	records []application.EventRecord,
) error {
	documents := make([]elasticsearchBulkDocument, 0, len(records)*2)
	for _, record := range records {
		index, err := dailyElasticsearchIndex(
			s.config.RawIndex,
			record.OccurredAt,
		)
		if err != nil {
			return fmt.Errorf("resolve Elasticsearch raw index: %w", err)
		}
		documents = append(documents, elasticsearchBulkDocument{
			Index:  index,
			ID:     batchDocumentID(batchKey, record.BatchIndex),
			Source: stringFieldsToAny(eventRecordFields(record)),
		})
	}
	rollups, err := buildEventRollupDocuments(
		s.config.AggregateIndex,
		batchKey,
		records,
	)
	if err != nil {
		return err
	}
	documents = append(documents, rollups...)
	if err := s.bulkIndex(ctx, documents); err != nil {
		return fmt.Errorf("index Elasticsearch product telemetry: %w", err)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) RepairEventBatch(
	ctx context.Context,
	batchKey string,
	records []application.EventRecord,
) error {
	return s.PutEventBatch(ctx, batchKey, records)
}

func (s *ElasticsearchEventLogStore) HasEventBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	rawDocuments, complete, err := s.batchDocuments(
		ctx,
		elasticsearchIndexPattern(s.config.RawIndex),
		batchKey,
		expected,
	)
	if err != nil || !complete {
		return complete, err
	}
	records, err := eventRecordsFromElasticsearchDocuments(rawDocuments)
	if err != nil {
		return false, err
	}
	rollups, err := buildEventRollupDocuments(
		s.config.AggregateIndex,
		batchKey,
		records,
	)
	if err != nil {
		return false, err
	}
	rollupIDs := make([]string, 0, len(rollups))
	for _, rollup := range rollups {
		rollupIDs = append(rollupIDs, rollup.ID)
	}
	complete, err = s.hasDocumentIDs(
		ctx,
		elasticsearchIndexPattern(s.config.AggregateIndex),
		rollupIDs,
	)
	if err != nil || complete {
		return complete, err
	}
	if err := s.bulkIndex(ctx, rollups); err != nil {
		return false, fmt.Errorf(
			"repair Elasticsearch event rollups: %w",
			err,
		)
	}
	return s.hasDocumentIDs(
		ctx,
		elasticsearchIndexPattern(s.config.AggregateIndex),
		rollupIDs,
	)
}

func (s *ElasticsearchEventLogStore) PutStartupDiagnostics(
	ctx context.Context,
	batchKey string,
	records []application.StartupDiagnosticRecord,
) error {
	now := s.now().UTC()
	documents := make([]elasticsearchBulkDocument, 0, len(records))
	for position, record := range records {
		index, err := dailyElasticsearchIndex(
			s.config.StartupDiagnosticIndex,
			record.OccurredAt,
		)
		if err != nil {
			return fmt.Errorf(
				"resolve Elasticsearch startup diagnostic index: %w",
				err,
			)
		}
		documents = append(documents, elasticsearchBulkDocument{
			Index: index,
			ID:    batchDocumentID(batchKey, position),
			Source: map[string]any{
				"eventId":         record.EventID,
				"attemptId":       record.AttemptID,
				"phase":           record.Phase,
				"outcome":         record.Outcome,
				"occurredAt":      record.OccurredAt,
				"platform":        record.Platform,
				"runtimeEnv":      record.RuntimeEnv,
				"appVersion":      record.AppVersion,
				"networkClass":    record.NetworkClass,
				"recoverySurface": record.RecoverySurface,
				"failureCode":     record.FailureCode,
				"failureSource":   record.FailureSource,
				"deadlineOrigin":  record.DeadlineOrigin,
				"sequence":        record.Sequence,
				"phaseDurationMs": record.PhaseDurationMS,
				"elapsedMs":       record.ElapsedMS,
				"_batchKey":       batchKey,
				"_batchIndex":     position,
				"ingestedAt":      now.Format(time.RFC3339Nano),
			},
		})
	}
	if err := s.bulkIndex(ctx, documents); err != nil {
		return fmt.Errorf("index Elasticsearch startup diagnostics: %w", err)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) RepairStartupDiagnosticBatch(
	ctx context.Context,
	batchKey string,
	records []application.StartupDiagnosticRecord,
) error {
	return s.PutStartupDiagnostics(ctx, batchKey, records)
}

func (s *ElasticsearchEventLogStore) HasStartupDiagnosticBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	return s.hasBatch(
		ctx,
		elasticsearchIndexPattern(s.config.StartupDiagnosticIndex),
		batchKey,
		expected,
	)
}

func (s *ElasticsearchEventLogStore) PutRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	records []application.RuntimeLogRecord,
) error {
	documents := make([]elasticsearchBulkDocument, 0, len(records)*2)
	for _, record := range records {
		fields := make(map[string]string, len(record.Fields)+3)
		for key, value := range record.Fields {
			if value != "" {
				fields[key] = value
			}
		}
		fields["_batchKey"] = batchKey
		fields["_batchIndex"] = strconv.Itoa(record.BatchIndex)
		fields["ingestedAt"] = record.IngestedAt.UTC().Format(time.RFC3339Nano)
		index, err := dailyElasticsearchIndex(
			s.config.RuntimeLogIndex,
			fields["occurredAt"],
		)
		if err != nil {
			return fmt.Errorf("resolve Elasticsearch runtime log index: %w", err)
		}
		documents = append(documents, elasticsearchBulkDocument{
			Index:  index,
			ID:     batchDocumentID(batchKey, record.BatchIndex),
			Source: stringFieldsToAny(fields),
		})
	}
	rollups, err := buildRuntimeLogRollupDocuments(
		s.config.AggregateIndex,
		batchKey,
		records,
	)
	if err != nil {
		return err
	}
	documents = append(documents, rollups...)
	if err := s.bulkIndex(ctx, documents); err != nil {
		return fmt.Errorf("index Elasticsearch runtime diagnostics: %w", err)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) RepairRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	records []application.RuntimeLogRecord,
) error {
	return s.PutRuntimeLogBatch(ctx, batchKey, records)
}

func (s *ElasticsearchEventLogStore) HasRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	expected int,
) (bool, error) {
	rawDocuments, complete, err := s.batchDocuments(
		ctx,
		elasticsearchIndexPattern(s.config.RuntimeLogIndex),
		batchKey,
		expected,
	)
	if err != nil || !complete {
		return complete, err
	}
	records, err := runtimeLogRecordsFromElasticsearchDocuments(rawDocuments)
	if err != nil {
		return false, err
	}
	rollups, err := buildRuntimeLogRollupDocuments(
		s.config.AggregateIndex,
		batchKey,
		records,
	)
	if err != nil {
		return false, err
	}
	rollupIDs := make([]string, 0, len(rollups))
	for _, rollup := range rollups {
		rollupIDs = append(rollupIDs, rollup.ID)
	}
	complete, err = s.hasDocumentIDs(
		ctx,
		elasticsearchIndexPattern(s.config.AggregateIndex),
		rollupIDs,
	)
	if err != nil || complete {
		return complete, err
	}
	if err := s.bulkIndex(ctx, rollups); err != nil {
		return false, fmt.Errorf(
			"repair Elasticsearch runtime rollups: %w",
			err,
		)
	}
	return s.hasDocumentIDs(
		ctx,
		elasticsearchIndexPattern(s.config.AggregateIndex),
		rollupIDs,
	)
}

type elasticsearchBulkDocument struct {
	Index  string
	ID     string
	Source map[string]any
}

func (s *ElasticsearchEventLogStore) bulkIndex(
	ctx context.Context,
	documents []elasticsearchBulkDocument,
) error {
	if len(documents) == 0 {
		return nil
	}
	var payload bytes.Buffer
	encoder := json.NewEncoder(&payload)
	encoder.SetEscapeHTML(false)
	for _, document := range documents {
		if err := encoder.Encode(map[string]any{
			"index": map[string]any{
				"_index": document.Index,
				"_id":    document.ID,
			},
		}); err != nil {
			return fmt.Errorf("encode Elasticsearch bulk metadata: %w", err)
		}
		if err := encoder.Encode(document.Source); err != nil {
			return fmt.Errorf("encode Elasticsearch bulk document: %w", err)
		}
	}
	status, body, err := s.request(
		ctx,
		http.MethodPost,
		"/_bulk?refresh=wait_for",
		payload.Bytes(),
		"application/x-ndjson",
	)
	if err != nil {
		return err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return fmt.Errorf(
			"Elasticsearch bulk status=%d: %s",
			status,
			truncateElasticsearchBody(body),
		)
	}
	var response struct {
		Errors bool `json:"errors"`
		Items  []map[string]struct {
			Status int             `json:"status"`
			Error  json.RawMessage `json:"error"`
		} `json:"items"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return fmt.Errorf("decode Elasticsearch bulk response: %w", err)
	}
	if response.Errors {
		for _, item := range response.Items {
			for operation, result := range item {
				if result.Status >= http.StatusMultipleChoices {
					return fmt.Errorf(
						"Elasticsearch bulk %s status=%d: %s",
						operation,
						result.Status,
						truncateElasticsearchBody(result.Error),
					)
				}
			}
		}
		return fmt.Errorf("Elasticsearch bulk reported item errors")
	}
	return nil
}

func (s *ElasticsearchEventLogStore) hasBatch(
	ctx context.Context,
	index string,
	batchKey string,
	expected int,
) (bool, error) {
	if expected <= 0 {
		return false, nil
	}
	ids := make([]string, expected)
	for index := range ids {
		ids[index] = batchDocumentID(batchKey, index)
	}
	_, complete, err := s.searchDocumentsByIDs(ctx, index, ids)
	return complete, err
}

func (s *ElasticsearchEventLogStore) batchDocuments(
	ctx context.Context,
	index string,
	batchKey string,
	expected int,
) ([]map[string]any, bool, error) {
	if expected <= 0 {
		return nil, false, nil
	}
	ids := make([]string, expected)
	for index := range ids {
		ids[index] = batchDocumentID(batchKey, index)
	}
	return s.searchDocumentsByIDs(ctx, index, ids)
}

func (s *ElasticsearchEventLogStore) hasDocumentIDs(
	ctx context.Context,
	index string,
	ids []string,
) (bool, error) {
	if len(ids) == 0 {
		return false, nil
	}
	_, complete, err := s.searchDocumentsByIDs(ctx, index, ids)
	return complete, err
}

func (s *ElasticsearchEventLogStore) searchDocumentsByIDs(
	ctx context.Context,
	index string,
	ids []string,
) ([]map[string]any, bool, error) {
	if len(ids) == 0 {
		return nil, false, nil
	}
	var response struct {
		Hits elasticsearchHits `json:"hits"`
	}
	if err := s.search(ctx, index, map[string]any{
		"size":             len(ids),
		"track_total_hits": true,
		"query": map[string]any{
			"ids": map[string]any{"values": ids},
		},
	}, &response); err != nil {
		return nil, false, fmt.Errorf(
			"search Elasticsearch deterministic documents: %w",
			err,
		)
	}
	if response.Hits.Total.Value != int64(len(ids)) {
		return nil, false, nil
	}
	byID := make(map[string]map[string]any, len(response.Hits.Hits))
	for _, hit := range response.Hits.Hits {
		if _, exists := byID[hit.ID]; exists {
			return nil, false, fmt.Errorf(
				"Elasticsearch deterministic document id %q exists in multiple daily indices",
				hit.ID,
			)
		}
		byID[hit.ID] = hit.Source
	}
	documents := make([]map[string]any, 0, len(ids))
	for _, id := range ids {
		document, found := byID[id]
		if !found {
			return nil, false, nil
		}
		documents = append(documents, document)
	}
	return documents, true, nil
}

func (s *ElasticsearchEventLogStore) search(
	ctx context.Context,
	index string,
	query map[string]any,
	result any,
) error {
	status, body, err := s.request(
		ctx,
		http.MethodPost,
		"/"+index+"/_search",
		query,
		"application/json",
	)
	if err != nil {
		return err
	}
	if status < http.StatusOK || status >= http.StatusMultipleChoices {
		return fmt.Errorf(
			"Elasticsearch search status=%d: %s",
			status,
			truncateElasticsearchBody(body),
		)
	}
	if err := json.Unmarshal(body, result); err != nil {
		return fmt.Errorf("decode Elasticsearch search response: %w", err)
	}
	return nil
}

func (s *ElasticsearchEventLogStore) request(
	ctx context.Context,
	method string,
	path string,
	body any,
	contentType string,
) (int, []byte, error) {
	var reader io.Reader
	switch typed := body.(type) {
	case nil:
	case []byte:
		reader = bytes.NewReader(typed)
	default:
		encoded, err := json.Marshal(typed)
		if err != nil {
			return 0, nil, fmt.Errorf("encode Elasticsearch request: %w", err)
		}
		reader = bytes.NewReader(encoded)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		method,
		s.config.Endpoint+path,
		reader,
	)
	if err != nil {
		return 0, nil, fmt.Errorf("build Elasticsearch request: %w", err)
	}
	request.Header.Set("Accept", "application/json")
	if s.config.APIKey != "" {
		request.Header.Set("Authorization", "ApiKey "+s.config.APIKey)
	}
	if reader != nil {
		request.Header.Set("Content-Type", contentType)
	}
	response, err := s.client.Do(request)
	if err != nil {
		return 0, nil, fmt.Errorf("execute Elasticsearch request: %w", err)
	}
	defer response.Body.Close()
	payload, err := io.ReadAll(
		io.LimitReader(response.Body, maxElasticsearchResponseBytes+1),
	)
	if err != nil {
		return 0, nil, fmt.Errorf("read Elasticsearch response: %w", err)
	}
	if len(payload) > maxElasticsearchResponseBytes {
		return 0, nil, fmt.Errorf("Elasticsearch response exceeds size limit")
	}
	return response.StatusCode, payload, nil
}

func batchDocumentID(batchKey string, index int) string {
	return batchKey + ":" + strconv.Itoa(index)
}

func stringFieldsToAny(fields map[string]string) map[string]any {
	out := make(map[string]any, len(fields))
	for key, value := range fields {
		out[key] = value
	}
	return out
}

func dailyElasticsearchIndex(base string, timestamp string) (string, error) {
	parsed, err := time.Parse(time.RFC3339Nano, timestamp)
	if err != nil {
		return "", fmt.Errorf("parse index timestamp: %w", err)
	}
	return dailyElasticsearchIndexForTime(base, parsed.UTC()), nil
}

func dailyElasticsearchIndexForTime(base string, instant time.Time) string {
	return base + "-" + instant.UTC().Format("2006.01.02")
}

func elasticsearchIndexPattern(base string) string {
	return base + "-*"
}

func truncateElasticsearchBody(body []byte) string {
	const limit = 512
	if len(body) <= limit {
		return string(body)
	}
	return string(body[:limit]) + "…"
}

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

func elasticsearchRawIndexDefinition() map[string]any {
	properties := map[string]any{
		"occurredAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
		"ingestedAt":  map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
		"_batchIndex": map[string]any{"type": "integer"},
	}
	for _, field := range []string{
		"durationMs",
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
	} {
		properties[field] = map[string]any{"type": "long", "coerce": true}
	}
	for _, field := range []string{
		"hasError",
		"decoderFallbackEnabled",
		"durationMismatch",
		"mediaConnected",
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
				"occurredAt":      map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"ingestedAt":      map[string]any{"type": "date", "format": "strict_date_optional_time_nanos"},
				"_batchIndex":     map[string]any{"type": "integer"},
				"sequence":        map[string]any{"type": "integer"},
				"phaseDurationMs": map[string]any{"type": "long"},
				"elapsedMs":       map[string]any{"type": "long"},
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
