package persistence

import (
	"context"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/product-ops-service/internal/application"
)

// MemoryTelemetryStore 仅用于 local_contract；生产装配必须注入真实存储 adapter。
type MemoryTelemetryStore struct {
	mu     sync.RWMutex
	events map[string]application.EventDrilldownItem
	visits map[string]application.VisitRecord
}

func NewMemoryTelemetryStore() *MemoryTelemetryStore {
	return &MemoryTelemetryStore{
		events: map[string]application.EventDrilldownItem{},
		visits: map[string]application.VisitRecord{},
	}
}

func (s *MemoryTelemetryStore) RecordVisit(_ context.Context, input application.VisitInput) (application.VisitRecord, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	key := visitKey(input.UserID, input.TargetType, input.TargetKey)
	record := s.visits[key]
	record.UserID = input.UserID
	record.TargetType = input.TargetType
	record.TargetKey = input.TargetKey
	record.VisitCount++
	record.LastSeenAt = nowRFC3339()
	record.SessionID = strings.TrimSpace(input.SessionID)
	record.Source = strings.TrimSpace(input.Source)
	s.visits[key] = record
	return record, nil
}

func (s *MemoryTelemetryStore) GetVisitStats(_ context.Context, query application.VisitStatsQuery) (application.VisitStats, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := application.VisitStats{Items: []application.VisitRecord{}}
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
	sort.Slice(out.Items, func(i, j int) bool {
		if out.Items[i].VisitCount == out.Items[j].VisitCount {
			return out.Items[i].TargetKey < out.Items[j].TargetKey
		}
		return out.Items[i].VisitCount > out.Items[j].VisitCount
	})
	return out, nil
}

func (s *MemoryTelemetryStore) ReportEventBatch(_ context.Context, events []application.EventRecordInput) (application.EventBatchAck, []application.EventDrilldownItem, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	ack := application.EventBatchAck{}
	inserted := make([]application.EventDrilldownItem, 0, len(events))
	for _, raw := range events {
		item := normalizeEvent(raw)
		if _, exists := s.events[item.EventID]; exists {
			ack.DuplicateCount++
			continue
		}
		s.events[item.EventID] = item
		ack.AcceptedCount++
		inserted = append(inserted, item)
	}
	return ack, inserted, nil
}

func (s *MemoryTelemetryStore) GetEventSummary(_ context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := s.matchEventsLocked(buildEventFilter(query))
	return summarizeEvents(items, query.EventType, query.EventName), nil
}

func (s *MemoryTelemetryStore) GetEventDrilldown(_ context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := s.matchEventsLocked(buildEventFilter(query))
	sort.Slice(items, func(i, j int) bool { return items[i].OccurredAt > items[j].OccurredAt })
	totalCount := int64(len(items))
	if query.Limit > 0 && len(items) > query.Limit {
		items = items[:query.Limit]
	}
	return application.EventDrilldown{
		TotalCount: totalCount,
		Items:      items,
	}, nil
}

func (s *MemoryTelemetryStore) matchEventsLocked(filter bson.D) []application.EventDrilldownItem {
	items := make([]application.EventDrilldownItem, 0, len(s.events))
	for _, item := range s.events {
		if matchesEventFilter(item, filter) {
			items = append(items, item)
		}
	}
	return items
}

func matchesEventFilter(item application.EventDrilldownItem, filter bson.D) bool {
	for _, clause := range filter {
		switch clause.Key {
		case "eventType":
			if item.EventType != clause.Value {
				return false
			}
		case "eventName":
			if item.EventName != clause.Value {
				return false
			}
		case "pageName":
			if item.PageName != clause.Value {
				return false
			}
		case "surfaceId":
			if item.SurfaceID != clause.Value {
				return false
			}
		case "routeId":
			if item.RouteID != clause.Value {
				return false
			}
		case "targetType":
			if item.TargetType != clause.Value {
				return false
			}
		case "targetKey":
			if item.TargetKey != clause.Value {
				return false
			}
		case "entityType":
			if item.EntityType != clause.Value {
				return false
			}
		case "entityId":
			if item.EntityID != clause.Value {
				return false
			}
		case "experimentBucket":
			if item.ExperimentBucket != clause.Value {
				return false
			}
		case "source":
			if item.Source != clause.Value {
				return false
			}
		case "occurredAt":
			rangeDoc, ok := clause.Value.(bson.D)
			if !ok || !withinTimeRange(item.OccurredAt, rangeDoc) {
				return false
			}
		}
	}
	return true
}

func withinTimeRange(raw string, rangeDoc bson.D) bool {
	parsed, err := time.Parse(time.RFC3339Nano, raw)
	if err != nil {
		return false
	}
	for _, clause := range rangeDoc {
		want, ok := clause.Value.(time.Time)
		if !ok {
			return false
		}
		switch clause.Key {
		case "$gte":
			if parsed.Before(want) {
				return false
			}
		case "$lte":
			if parsed.After(want) {
				return false
			}
		default:
			return false
		}
	}
	return true
}

func summarizeEvents(items []application.EventDrilldownItem, eventType, eventName string) application.EventSummary {
	out := application.EventSummary{
		EventType:         strings.TrimSpace(eventType),
		EventName:         strings.TrimSpace(eventName),
		DimensionCounters: map[string]map[string]int{},
	}
	for _, item := range items {
		out.TotalCount++
		if out.LatestOccurredAt == "" || item.OccurredAt > out.LatestOccurredAt {
			out.LatestOccurredAt = item.OccurredAt
		}
		addDimension(out.DimensionCounters, "pageName", item.PageName)
		addDimension(out.DimensionCounters, "surfaceId", item.SurfaceID)
		addDimension(out.DimensionCounters, "routeId", item.RouteID)
		addDimension(out.DimensionCounters, "experimentBucket", item.ExperimentBucket)
		addDimension(out.DimensionCounters, "targetKey", item.TargetKey)
		addDimension(out.DimensionCounters, "entityId", item.EntityID)
		addDimension(out.DimensionCounters, "errorCode", item.ErrorCode)
		addDimension(out.DimensionCounters, "nature", item.Nature)
		addDimension(out.DimensionCounters, "appRuntimeEnv", item.AppRuntimeEnv)
		addDimension(out.DimensionCounters, "source", item.Source)
		addDimension(out.DimensionCounters, "eventName", item.EventName)
	}
	return out
}

func addDimension(dimensions map[string]map[string]int, name, value string) {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return
	}
	if _, ok := dimensions[name]; !ok {
		dimensions[name] = map[string]int{}
	}
	dimensions[name][trimmed]++
}

func visitKey(userID, targetType, targetKey string) string {
	return strings.Join([]string{userID, targetType, targetKey}, "|")
}

var _ application.TelemetryStore = (*MemoryTelemetryStore)(nil)
