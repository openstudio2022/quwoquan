package persistence

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

func (s *PostgresTelemetryStore) runtimeRows(
	ctx context.Context,
	from, to time.Time,
) ([]postgresRuntimeRow, error) {
	rows, err := s.pool.Query(ctx, fmt.Sprintf(`
SELECT row_key,fields,ingested_at FROM %s
WHERE occurred_at >= $1 AND occurred_at < $2
ORDER BY occurred_at DESC,row_key DESC`,
		s.table("telemetry_runtime_records")), from.UTC(), to.UTC())
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make([]postgresRuntimeRow, 0)
	for rows.Next() {
		var row postgresRuntimeRow
		if err := rows.Scan(&row.rowKey, &row.fields, &row.ingestedAt); err != nil {
			return nil, err
		}
		out = append(out, row)
	}
	return out, rows.Err()
}

type postgresRuntimeRow struct {
	rowKey     string
	fields     []byte
	ingestedAt time.Time
}

func (s *PostgresTelemetryStore) GetRuntimeLogSummary(
	ctx context.Context,
	query application.RuntimeLogSummaryQuery,
) (application.RuntimeLogSummary, error) {
	rows, err := s.runtimeRows(ctx, query.From, query.To)
	if err != nil {
		return application.RuntimeLogSummary{}, err
	}
	out := application.RuntimeLogSummary{
		TotalCount:        int64(len(rows)),
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "raw_records",
		Freshness:         "near_realtime",
		GeneratedThrough:  query.To.UTC().Format(time.RFC3339Nano),
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	for _, row := range rows {
		fields := map[string]string{}
		if err := json.Unmarshal(row.fields, &fields); err != nil {
			return application.RuntimeLogSummary{}, err
		}
		if !runtimeFieldsMatch(fields, query) {
			out.TotalCount--
			continue
		}
		for dimension, value := range map[string]string{
			"signal": fields["signal"], "severity": fields["severity"],
			"errorCode": fields["errorCode"], "sourceType": fields["resourceSourceType"],
			"service": fields["resourceService"], "appVersion": fields["resourceAppVersion"],
		} {
			if strings.TrimSpace(value) == "" {
				continue
			}
			if out.DimensionCounters[dimension] == nil {
				out.DimensionCounters[dimension] = map[string]int{}
			}
			out.DimensionCounters[dimension][value]++
		}
	}
	return out, nil
}

func runtimeFieldsMatch(fields map[string]string, query application.RuntimeLogSummaryQuery) bool {
	return (query.Signal == "" || fields["signal"] == query.Signal) &&
		(query.Severity == "" || fields["severity"] == query.Severity) &&
		(query.ErrorCode == "" || fields["errorCode"] == query.ErrorCode) &&
		(query.Fingerprint == "" || fields["fingerprint"] == query.Fingerprint) &&
		(query.SourceType == "" || fields["resourceSourceType"] == query.SourceType) &&
		(query.Service == "" || fields["resourceService"] == query.Service) &&
		(query.AppVersion == "" || fields["resourceAppVersion"] == query.AppVersion)
}

func (s *PostgresTelemetryStore) GetRuntimeLogDrilldown(
	ctx context.Context,
	query application.RuntimeLogDrilldownQuery,
) (application.RuntimeLogDrilldown, error) {
	rows, err := s.runtimeRows(ctx, query.From, query.To)
	if err != nil {
		return application.RuntimeLogDrilldown{}, err
	}
	out := application.RuntimeLogDrilldown{
		Items:            make([]application.RuntimeLogDrilldownItem, 0),
		SourceKind:       "raw_records",
		Freshness:        "near_realtime",
		GeneratedThrough: query.To.UTC().Format(time.RFC3339Nano),
		ActualFrom:       query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:         query.To.UTC().Format(time.RFC3339Nano),
	}
	limit := query.Limit
	if limit <= 0 || limit > 100 {
		limit = 50
	}
	for _, row := range rows {
		fields := map[string]string{}
		if err := json.Unmarshal(row.fields, &fields); err != nil {
			return application.RuntimeLogDrilldown{}, err
		}
		if !runtimeFieldsMatch(fields, application.RuntimeLogSummaryQuery{
			Signal: query.Signal, Severity: query.Severity, ErrorCode: query.ErrorCode,
			Fingerprint: query.Fingerprint, SourceType: query.SourceType,
			Service: query.Service, AppVersion: query.AppVersion,
		}) {
			continue
		}
		out.TotalCount++
		if len(out.Items) >= limit {
			continue
		}
		out.Items = append(out.Items, runtimeDrilldownItem(row.rowKey, row.ingestedAt, fields, query.RevealCorrelation))
	}
	return out, nil
}

func runtimeDrilldownItem(
	rowKey string,
	ingestedAt time.Time,
	fields map[string]string,
	revealCorrelation bool,
) application.RuntimeLogDrilldownItem {
	resource := map[string]string{}
	for _, key := range []string{
		"resourceSourceType", "resourceService", "resourceAppVersion",
		"resourceEnvironment", "resourceRegion",
	} {
		if fields[key] != "" {
			resource[key] = fields[key]
		}
	}
	correlation := map[string]string{}
	if revealCorrelation {
		for _, key := range []string{"requestId", "traceId", "operationId"} {
			if fields[key] != "" {
				correlation[key] = fields[key]
			}
		}
	}
	attributes := map[string]string{}
	for key, value := range fields {
		if strings.HasPrefix(key, "attribute.") {
			attributes[strings.TrimPrefix(key, "attribute.")] = value
		}
	}
	return application.RuntimeLogDrilldownItem{
		RowKey: rowKey, RecordID: fields["recordId"],
		OccurredAt: fields["occurredAt"], ObservedAt: fields["observedAt"],
		LogKind: fields["logKind"], Severity: fields["severity"], Signal: fields["signal"],
		Message: fields["message"], ErrorCode: fields["errorCode"], Fingerprint: fields["fingerprint"],
		Resource: resource, Correlation: correlation, Attributes: attributes,
		IngestedAt: ingestedAt.UTC().Format(time.RFC3339Nano),
	}
}
