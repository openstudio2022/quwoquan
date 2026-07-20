package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

// MemoryTelemetryStore 仅用于 local_contract；生产装配为 MongoVisitStore +
// SLSEventLogStore + RedisEventBatchLedger。
type MemoryTelemetryStore struct {
	mu             sync.Mutex
	visits         map[string]application.VisitRecord
	events         []application.EventRecord
	batchStates    map[string]application.BatchLedgerState
	batchCounts    map[string]int
	startup        []application.StartupDiagnosticRecord
	startupBatches map[string]int
	runtimeLogs    []application.RuntimeLogRecord
	runtimeBatches map[string]int
}

func NewMemoryTelemetryStore() *MemoryTelemetryStore {
	return &MemoryTelemetryStore{
		visits:         map[string]application.VisitRecord{},
		batchStates:    map[string]application.BatchLedgerState{},
		batchCounts:    map[string]int{},
		startupBatches: map[string]int{},
		runtimeBatches: map[string]int{},
	}
}

func (s *MemoryTelemetryStore) RecordVisit(_ context.Context, input application.VisitInput) (application.VisitRecord, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := input.UserID + ":" + input.TargetType + ":" + input.TargetKey
	record := s.visits[key]
	record.UserID, record.TargetType, record.TargetKey = input.UserID, input.TargetType, input.TargetKey
	record.VisitCount++
	record.LastSeenAt = time.Now().UTC().Format(time.RFC3339Nano)
	record.SessionID, record.Source = input.SessionID, input.Source
	s.visits[key] = record
	return record, nil
}

func (s *MemoryTelemetryStore) GetVisit(_ context.Context, userID, targetType, targetKey string) (application.VisitRecord, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	record, ok := s.visits[userID+":"+targetType+":"+targetKey]
	return record, ok, nil
}

func (s *MemoryTelemetryStore) GetVisitStats(_ context.Context, query application.VisitStatsQuery) (application.VisitStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := application.VisitStats{}
	for _, item := range s.visits {
		if query.TargetType != "" && item.TargetType != query.TargetType {
			continue
		}
		if query.TargetKey != "" && item.TargetKey != query.TargetKey {
			continue
		}
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	return out, nil
}

func (s *MemoryTelemetryStore) Begin(_ context.Context, batchKey string, count int) (application.BatchLedgerState, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if state, ok := s.batchStates[batchKey]; ok {
		return state, nil
	}
	s.batchStates[batchKey] = application.BatchLedgerPending
	s.batchCounts[batchKey] = count
	return application.BatchLedgerNew, nil
}

func (s *MemoryTelemetryStore) MarkAccepted(_ context.Context, batchKey string, count int) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.batchStates[batchKey], s.batchCounts[batchKey] = application.BatchLedgerAccepted, count
	return nil
}

func (s *MemoryTelemetryStore) PutEventBatch(_ context.Context, _ string, records []application.EventRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.events = append(s.events, records...)
	return nil
}

// ReadRtcMediaQoeSummary 为 local_contract 提供与生产 SLS/Postgres reader
// 相同的分母、原始样本 P95 和 UTC 小时桶语义。
func (s *MemoryTelemetryStore) ReadRtcMediaQoeSummary(
	_ context.Context,
	query application.RtcMediaQoeSummaryQuery,
) (application.RtcMediaQoeSummarySlice, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	hourly := make(map[time.Time]*rtcMediaQoeMemoryAggregate)
	total := &rtcMediaQoeMemoryAggregate{}
	for _, event := range s.events {
		if event.EventType != "rtc_media_qoe" || event.Result == nil ||
			strings.TrimSpace(*event.Result) == "" || *event.Result == "abandoned" {
			continue
		}
		occurredAt, err := time.Parse(time.RFC3339Nano, event.OccurredAt)
		if err != nil || occurredAt.Before(query.From) || !occurredAt.Before(query.To) {
			continue
		}
		bucket := occurredAt.UTC().Truncate(time.Hour)
		aggregate := hourly[bucket]
		if aggregate == nil {
			aggregate = &rtcMediaQoeMemoryAggregate{}
			hourly[bucket] = aggregate
		}
		aggregate.add(event)
		total.add(event)
	}

	rows := make([]application.RtcMediaQoeAggregate, 0, len(hourly))
	for bucket, aggregate := range hourly {
		row := aggregate.build()
		row.BucketStart = bucket
		rows = append(rows, row)
	}
	sort.Slice(rows, func(left, right int) bool {
		return rows[left].BucketStart.Before(rows[right].BucketStart)
	})
	return application.BuildRtcMediaQoeSummary(
		query,
		rows,
		total.build(),
		"raw_records",
	), nil
}

type rtcMediaQoeMemoryAggregate struct {
	effective        int64
	connected        int64
	connectionLost   int64
	reconnectCount   int64
	connectTimeMS    []float64
	generatedThrough *time.Time
}

func (a *rtcMediaQoeMemoryAggregate) add(event application.EventRecord) {
	a.effective++
	if event.ReconnectCount != nil {
		a.reconnectCount += int64(*event.ReconnectCount)
	}
	if event.IngestedAt.After(optionalTimeValue(a.generatedThrough)) {
		value := event.IngestedAt.UTC()
		a.generatedThrough = &value
	}
	if event.MediaConnected == nil || !*event.MediaConnected {
		return
	}
	a.connected++
	if event.ConnectTimeMS != nil {
		a.connectTimeMS = append(a.connectTimeMS, float64(*event.ConnectTimeMS))
	}
	if event.Result != nil && *event.Result == "connection_lost" {
		a.connectionLost++
	}
}

func (a *rtcMediaQoeMemoryAggregate) build() application.RtcMediaQoeAggregate {
	return application.RtcMediaQoeAggregate{
		EffectiveSampleCount: a.effective,
		MediaConnectedCount:  a.connected,
		ConnectP95MS:         percentileCont95(a.connectTimeMS),
		ConnectionLostCount:  a.connectionLost,
		ReconnectCount:       a.reconnectCount,
		GeneratedThrough:     a.generatedThrough,
	}
}

func percentileCont95(values []float64) *float64 {
	if len(values) == 0 {
		return nil
	}
	sorted := append([]float64(nil), values...)
	sort.Float64s(sorted)
	rank := float64(len(sorted)-1) * 0.95
	lower := int(rank)
	upper := lower + 1
	if upper >= len(sorted) {
		value := sorted[lower]
		return &value
	}
	value := sorted[lower] + (sorted[upper]-sorted[lower])*(rank-float64(lower))
	return &value
}

func optionalTimeValue(value *time.Time) time.Time {
	if value == nil {
		return time.Time{}
	}
	return *value
}

func (s *MemoryTelemetryStore) HasEventBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	count := 0
	for _, event := range s.events {
		if event.BatchKey == batchKey {
			count++
		}
	}
	return count == expected, nil
}

func (s *MemoryTelemetryStore) PutStartupDiagnostics(_ context.Context, batchKey string, records []application.StartupDiagnosticRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.startup = append(s.startup, records...)
	s.startupBatches[batchKey] += len(records)
	return nil
}

func (s *MemoryTelemetryStore) HasStartupDiagnosticBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.startupBatches[batchKey] == expected, nil
}

func (s *MemoryTelemetryStore) PutRuntimeLogBatch(_ context.Context, batchKey string, records []application.RuntimeLogRecord) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runtimeLogs = append(s.runtimeLogs, records...)
	s.runtimeBatches[batchKey] += len(records)
	return nil
}

func (s *MemoryTelemetryStore) HasRuntimeLogBatch(_ context.Context, batchKey string, expected int) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.runtimeBatches[batchKey] == expected, nil
}

func (s *MemoryTelemetryStore) GetRuntimeLogSummary(_ context.Context, query application.RuntimeLogSummaryQuery) (application.RuntimeLogSummary, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := application.RuntimeLogSummary{
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "hourly_rollup",
		Freshness:         "near_realtime",
		ActualFrom:        query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:          query.To.UTC().Format(time.RFC3339Nano),
	}
	for _, record := range s.runtimeLogs {
		if !matchesRuntimeLog(record, query.Signal, query.Severity, query.ErrorCode, query.Fingerprint, query.SourceType, query.Service, query.AppVersion, query.From, query.To) {
			continue
		}
		out.TotalCount++
		for name, value := range map[string]string{
			"logKind":     record.Fields["logKind"],
			"severity":    record.Fields["severity"],
			"signal":      record.Fields["signal"],
			"errorCode":   record.Fields["errorCode"],
			"fingerprint": record.Fields["fingerprint"],
			"sourceType":  record.Fields["resourceSourceType"],
			"service":     record.Fields["resourceService"],
			"appVersion":  record.Fields["resourceAppVersion"],
		} {
			addDimension(out.DimensionCounters, name, value)
		}
	}
	return out, nil
}

func (s *MemoryTelemetryStore) GetRuntimeLogDrilldown(_ context.Context, query application.RuntimeLogDrilldownQuery) (application.RuntimeLogDrilldown, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	matched := make([]application.RuntimeLogRecord, 0)
	for _, record := range s.runtimeLogs {
		if !matchesRuntimeLog(record, query.Signal, query.Severity, query.ErrorCode, query.Fingerprint, query.SourceType, query.Service, query.AppVersion, query.From, query.To) {
			continue
		}
		if query.ActorHash != "" && record.Fields["actorHash"] != query.ActorHash {
			continue
		}
		if query.MessageContains != "" && !strings.Contains(record.Fields["message"], query.MessageContains) {
			continue
		}
		matched = append(matched, record)
	}
	sort.Slice(matched, func(i, j int) bool { return matched[i].IngestedAt.After(matched[j].IngestedAt) })
	total := len(matched)
	if len(matched) > query.Limit {
		matched = matched[:query.Limit]
	}
	items := make([]application.RuntimeLogDrilldownItem, 0, len(matched))
	for _, record := range matched {
		items = append(items, runtimeLogDrilldownItem(record, query.RevealCorrelation))
	}
	return application.RuntimeLogDrilldown{
		TotalCount: int64(total),
		Items:      items,
		SourceKind: "raw_records",
		Freshness:  "near_realtime",
		ActualFrom: query.From.UTC().Format(time.RFC3339Nano),
		ActualTo:   query.To.UTC().Format(time.RFC3339Nano),
	}, nil
}

func (s *MemoryTelemetryStore) GetEventSummary(_ context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := application.EventSummary{
		DimensionCounters: map[string]map[string]int{},
		SourceKind:        "hourly_rollup", Freshness: "near_realtime",
		ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano),
	}
	sessions := map[string]struct{}{}
	for _, event := range s.events {
		if !matches(event, query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode, query.From, query.To) {
			continue
		}
		out.TotalCount++
		sessions[event.SessionID] = struct{}{}
		addDimension(out.DimensionCounters, "logType", event.LogType)
		addDimension(out.DimensionCounters, "eventType", event.EventType)
		addDimension(out.DimensionCounters, "pageName", event.PageName)
		addDimension(out.DimensionCounters, "appVersion", event.AppVersion)
		addDimension(out.DimensionCounters, "networkClass", event.NetworkClass)
		addDimension(out.DimensionCounters, "deviceManufacturer", event.DeviceManufacturer)
		addDimension(out.DimensionCounters, "deviceModel", event.DeviceModel)
		if event.Journey != nil {
			addDimension(out.DimensionCounters, "journey", *event.Journey)
		}
		if event.Action != nil {
			addDimension(out.DimensionCounters, "action", *event.Action)
		}
		if event.Result != nil {
			addDimension(out.DimensionCounters, "result", *event.Result)
		}
		if event.ErrorCode != nil {
			addDimension(out.DimensionCounters, "errorCode", *event.ErrorCode)
		}
	}
	out.SessionCount = int64(len(sessions))
	return out, nil
}

func (s *MemoryTelemetryStore) GetEventDrilldown(_ context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	matched := make([]application.EventRecord, 0)
	for _, event := range s.events {
		if matches(event, query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode, query.From, query.To) &&
			(query.SessionID == "" || event.SessionID == query.SessionID) {
			matched = append(matched, event)
		}
	}
	sort.Slice(matched, func(i, j int) bool { return matched[i].IngestedAt.After(matched[j].IngestedAt) })
	total := len(matched)
	if len(matched) > query.Limit {
		matched = matched[:query.Limit]
	}
	items := make([]application.EventDrilldownItem, 0, len(matched))
	for _, event := range matched {
		items = append(items, eventToDrilldown(event, query.RevealSession))
	}
	return application.EventDrilldown{
		TotalCount: int64(total), Items: items, SourceKind: "raw_records", Freshness: "near_realtime",
		ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano),
	}, nil
}

// GetPageExperienceStats 按 pageName 聚合页面体验事实（热力图数据源）。
func (s *MemoryTelemetryStore) GetPageExperienceStats(
	_ context.Context,
	query application.PageExperienceQuery,
) ([]application.PageExperienceStat, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	byPage := map[string]*application.PageExperienceStat{}
	ensure := func(pageName string) *application.PageExperienceStat {
		if stat, exists := byPage[pageName]; exists {
			return stat
		}
		stat := &application.PageExperienceStat{PageName: pageName}
		byPage[pageName] = stat
		return stat
	}
	readySum := map[string]float64{}
	staySum := map[string]float64{}
	for _, event := range s.events {
		occurredAt, err := time.Parse(time.RFC3339Nano, event.OccurredAt)
		if err != nil || occurredAt.Before(query.From) || !occurredAt.Before(query.To) {
			continue
		}
		if event.PageName == "" {
			continue
		}
		stat := ensure(event.PageName)
		switch event.EventType {
		case "page_open":
			stat.Opens++
			if event.ReadyMS != nil {
				stat.ReadySamples++
				readySum[event.PageName] += float64(*event.ReadyMS)
			}
		case "page_return":
			if event.DurationMS != nil {
				stat.StaySamples++
				staySum[event.PageName] += float64(*event.DurationMS)
			}
		case "runtime_exception":
			stat.RuntimeErrors++
		}
	}
	out := make([]application.PageExperienceStat, 0, len(byPage))
	for pageName, stat := range byPage {
		if stat.ReadySamples > 0 {
			stat.AvgReadyMs = readySum[pageName] / float64(stat.ReadySamples)
		}
		if stat.StaySamples > 0 {
			stat.AvgStayMs = staySum[pageName] / float64(stat.StaySamples)
		}
		out = append(out, *stat)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Opens > out[j].Opens })
	return out, nil
}

// ListDistinctSessions 返回窗口内 distinct sessionId 与事件总数（增长聚合用）。
func (s *MemoryTelemetryStore) ListDistinctSessions(
	_ context.Context,
	from, to time.Time,
	limit int,
) ([]string, int64, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	sessions := map[string]struct{}{}
	var totalEvents int64
	for _, event := range s.events {
		occurredAt, err := time.Parse(time.RFC3339Nano, event.OccurredAt)
		if err != nil || occurredAt.Before(from) || !occurredAt.Before(to) {
			continue
		}
		totalEvents++
		if len(sessions) < limit {
			sessions[event.SessionID] = struct{}{}
		}
	}
	out := make([]string, 0, len(sessions))
	for sessionID := range sessions {
		out = append(out, sessionID)
	}
	sort.Strings(out)
	return out, totalEvents, nil
}

func matches(event application.EventRecord, logType, eventType, pageName, appVersion, networkClass, errorCode string, from, to time.Time) bool {
	occurredAt, err := time.Parse(time.RFC3339Nano, event.OccurredAt)
	if err != nil {
		return false
	}
	if occurredAt.Before(from) || !occurredAt.Before(to) {
		return false
	}
	if logType != "" && event.LogType != logType || eventType != "" && event.EventType != eventType || pageName != "" && event.PageName != pageName || appVersion != "" && event.AppVersion != appVersion || networkClass != "" && event.NetworkClass != networkClass {
		return false
	}
	return errorCode == "" || event.ErrorCode != nil && *event.ErrorCode == errorCode
}

func matchesRuntimeLog(record application.RuntimeLogRecord, signal, severity, errorCode, fingerprint, sourceType, service, appVersion string, from, to time.Time) bool {
	occurredAt, err := time.Parse(time.RFC3339Nano, record.Fields["occurredAt"])
	if err != nil || occurredAt.Before(from) || !occurredAt.Before(to) {
		return false
	}
	fields := record.Fields
	return (signal == "" || fields["signal"] == signal) &&
		(severity == "" || fields["severity"] == severity) &&
		(errorCode == "" || fields["errorCode"] == errorCode) &&
		(fingerprint == "" || fields["fingerprint"] == fingerprint) &&
		(sourceType == "" || fields["resourceSourceType"] == sourceType) &&
		(service == "" || fields["resourceService"] == service) &&
		(appVersion == "" || fields["resourceAppVersion"] == appVersion)
}

func runtimeLogDrilldownItem(record application.RuntimeLogRecord, revealCorrelation bool) application.RuntimeLogDrilldownItem {
	fields := record.Fields
	rowDigest := sha256.Sum256([]byte(record.BatchKey + ":" + strconv.Itoa(record.BatchIndex)))
	resource := map[string]string{
		"sourceType": fields["resourceSourceType"],
		"service":    fields["resourceService"],
	}
	for raw, key := range map[string]string{
		"resourceEnvironment":    "environment",
		"resourceComponent":      "component",
		"resourceAppVersion":     "appVersion",
		"resourceServiceVersion": "service.version",
	} {
		if fields[raw] != "" {
			resource[key] = fields[raw]
		}
	}
	correlation := map[string]string{}
	if revealCorrelation {
		for _, key := range []string{"requestId", "traceId", "spanId", "operationId", "pageName", "surfaceId", "executionId", "workPackageId", "environmentRunId"} {
			if fields[key] != "" {
				correlation[key] = fields[key]
			}
		}
	}
	attributes := map[string]string{}
	_ = json.Unmarshal([]byte(fields["attributes"]), &attributes)
	return application.RuntimeLogDrilldownItem{
		RowKey:      hex.EncodeToString(rowDigest[:8]),
		RecordID:    fields["recordId"],
		OccurredAt:  fields["occurredAt"],
		ObservedAt:  fields["observedAt"],
		LogKind:     fields["logKind"],
		Severity:    fields["severity"],
		Signal:      fields["signal"],
		Message:     fields["message"],
		ErrorCode:   fields["errorCode"],
		Fingerprint: fields["fingerprint"],
		Resource:    resource,
		Correlation: correlation,
		Attributes:  attributes,
		IngestedAt:  record.IngestedAt.UTC().Format(time.RFC3339Nano),
	}
}

func addDimension(dimensions map[string]map[string]int, name, value string) {
	if value == "" {
		return
	}
	if dimensions[name] == nil {
		dimensions[name] = map[string]int{}
	}
	dimensions[name][value]++
}

func eventToDrilldown(event application.EventRecord, revealSession bool) application.EventDrilldownItem {
	digest := sha256.Sum256([]byte(event.BatchKey + ":" + strconv.Itoa(event.BatchIndex)))
	sessionID := event.SessionID
	if !revealSession {
		sessionID = maskSessionID(sessionID)
	}
	return application.EventDrilldownItem{
		RowKey: hex.EncodeToString(digest[:8]), LogType: event.LogType, EventType: event.EventType,
		SessionID: sessionID, PageName: event.PageName, OccurredAt: event.OccurredAt,
		DeviceManufacturer: event.DeviceManufacturer, DeviceModel: event.DeviceModel,
		AppVersion: event.AppVersion, NetworkClass: event.NetworkClass,
		DurationMS: event.DurationMS, Result: event.Result, FailReasonCode: event.FailReasonCode,
		ErrorCode: event.ErrorCode, OperationID: event.OperationID, HTTPStatus: event.HTTPStatus,
		CallStack: event.CallStack, TClickToFirstFrameMS: event.TClickToFirstFrameMS,
		TFirstFrameToShellMS: event.TFirstFrameToShellMS, TShellToContentMS: event.TShellToContentMS,
		TClickToContentMS: event.TClickToContentMS, HasError: event.HasError, Journey: event.Journey,
		Action: event.Action, IngestedAt: event.IngestedAt.UTC().Format(time.RFC3339Nano),
	}
}

func maskSessionID(value string) string {
	separator := strings.LastIndex(value, ".")
	if separator < 0 {
		return "***"
	}
	return "s.***" + value[separator:]
}

var _ application.VisitTelemetryStore = (*MemoryTelemetryStore)(nil)
var _ application.EventLogStore = (*MemoryTelemetryStore)(nil)
var _ application.EventBatchLedger = (*MemoryTelemetryStore)(nil)
var _ application.RuntimeLogStore = (*MemoryTelemetryStore)(nil)
