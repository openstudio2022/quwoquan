package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
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
}

func NewMemoryTelemetryStore() *MemoryTelemetryStore {
	return &MemoryTelemetryStore{
		visits:         map[string]application.VisitRecord{},
		batchStates:    map[string]application.BatchLedgerState{},
		batchCounts:    map[string]int{},
		startupBatches: map[string]int{},
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

func (s *MemoryTelemetryStore) GetEventSummary(_ context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := application.EventSummary{
		DimensionCounters: map[string]map[string]int{},
		Source:            "sls_aggregate", Freshness: "closed_hour",
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
		TotalCount: int64(total), Items: items, Source: "sls_raw", Freshness: "near_realtime",
		ActualFrom: query.From.UTC().Format(time.RFC3339Nano), ActualTo: query.To.UTC().Format(time.RFC3339Nano),
	}, nil
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

var _ application.TelemetryStore = (*MemoryTelemetryStore)(nil)
