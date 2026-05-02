package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/product-ops-service/internal/application"
)

type MongoTelemetryStore struct {
	eventColl *mongo.Collection
	visitColl *mongo.Collection
}

func NewMongoTelemetryStore(db *mongo.Database) *MongoTelemetryStore {
	return &MongoTelemetryStore{
		eventColl: db.Collection("event_records"),
		visitColl: db.Collection("visit_records"),
	}
}

func (s *MongoTelemetryStore) EnsureIndexes(ctx context.Context) error {
	eventIndexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "eventId", Value: 1}}, Options: options.Index().SetName("idx_event_event_id").SetUnique(true)},
		{Keys: bson.D{{Key: "eventType", Value: 1}, {Key: "eventName", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_type_name_time")},
		{Keys: bson.D{{Key: "pageName", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_page_time").SetSparse(true)},
		{Keys: bson.D{{Key: "surfaceId", Value: 1}, {Key: "routeId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_surface_route_time").SetSparse(true)},
		{Keys: bson.D{{Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_target_time").SetSparse(true)},
		{Keys: bson.D{{Key: "entityType", Value: 1}, {Key: "entityId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_entity_time").SetSparse(true)},
		{Keys: bson.D{{Key: "experimentBucket", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_experiment_time").SetSparse(true)},
	}
	visitIndexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}}, Options: options.Index().SetName("idx_visit_user_target").SetUnique(true)},
		{Keys: bson.D{{Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}, {Key: "lastSeenAt", Value: -1}}, Options: options.Index().SetName("idx_visit_target")},
		{Keys: bson.D{{Key: "sessionId", Value: 1}, {Key: "lastSeenAt", Value: -1}}, Options: options.Index().SetName("idx_visit_session").SetSparse(true)},
	}
	if _, err := s.eventColl.Indexes().CreateMany(ctx, eventIndexes); err != nil {
		return fmt.Errorf("create event indexes: %w", err)
	}
	if _, err := s.visitColl.Indexes().CreateMany(ctx, visitIndexes); err != nil {
		return fmt.Errorf("create visit indexes: %w", err)
	}
	return nil
}

func (s *MongoTelemetryStore) RecordVisit(ctx context.Context, input application.VisitInput) (application.VisitRecord, error) {
	now := nowRFC3339()
	filter := bson.D{
		{Key: "userId", Value: input.UserID},
		{Key: "targetType", Value: input.TargetType},
		{Key: "targetKey", Value: input.TargetKey},
	}
	setDoc := bson.D{
		{Key: "lastSeenAt", Value: now},
		{Key: "timestamp", Value: now},
	}
	if trimmed := strings.TrimSpace(input.SessionID); trimmed != "" {
		setDoc = append(setDoc, bson.E{Key: "sessionId", Value: trimmed})
	}
	if trimmed := strings.TrimSpace(input.Source); trimmed != "" {
		setDoc = append(setDoc, bson.E{Key: "source", Value: trimmed})
	}
	update := bson.D{
		{Key: "$inc", Value: bson.D{{Key: "visitCount", Value: 1}}},
		{Key: "$set", Value: setDoc},
		{Key: "$setOnInsert", Value: bson.D{
			{Key: "userId", Value: input.UserID},
			{Key: "targetType", Value: input.TargetType},
			{Key: "targetKey", Value: input.TargetKey},
		}},
	}
	opts := options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)
	var doc application.VisitRecord
	if err := s.visitColl.FindOneAndUpdate(ctx, filter, update, opts).Decode(&doc); err != nil {
		return application.VisitRecord{}, fmt.Errorf("record visit: %w", err)
	}
	return doc, nil
}

func (s *MongoTelemetryStore) GetVisitStats(ctx context.Context, query application.VisitStatsQuery) (application.VisitStats, error) {
	filter := bson.D{}
	if trimmed := strings.TrimSpace(query.TargetType); trimmed != "" {
		filter = append(filter, bson.E{Key: "targetType", Value: trimmed})
	}
	if trimmed := strings.TrimSpace(query.TargetKey); trimmed != "" {
		filter = append(filter, bson.E{Key: "targetKey", Value: trimmed})
	}
	cursor, err := s.visitColl.Find(ctx, filter)
	if err != nil {
		return application.VisitStats{}, fmt.Errorf("find visit stats: %w", err)
	}
	defer cursor.Close(ctx)
	out := application.VisitStats{Items: []application.VisitRecord{}}
	for cursor.Next(ctx) {
		var item application.VisitRecord
		if err := cursor.Decode(&item); err != nil {
			return application.VisitStats{}, fmt.Errorf("decode visit stat: %w", err)
		}
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	if err := cursor.Err(); err != nil {
		return application.VisitStats{}, fmt.Errorf("iterate visit stats: %w", err)
	}
	sort.Slice(out.Items, func(i, j int) bool {
		if out.Items[i].VisitCount == out.Items[j].VisitCount {
			return out.Items[i].TargetKey < out.Items[j].TargetKey
		}
		return out.Items[i].VisitCount > out.Items[j].VisitCount
	})
	return out, nil
}

func (s *MongoTelemetryStore) ReportEventBatch(ctx context.Context, events []application.EventRecordInput) (application.EventBatchAck, []application.EventDrilldownItem, error) {
	ack := application.EventBatchAck{}
	inserted := make([]application.EventDrilldownItem, 0, len(events))
	for _, raw := range events {
		item := normalizeEvent(raw)
		_, err := s.eventColl.InsertOne(ctx, item)
		if err != nil {
			if mongo.IsDuplicateKeyError(err) {
				ack.DuplicateCount++
				continue
			}
			return application.EventBatchAck{}, nil, fmt.Errorf("insert event %s: %w", item.EventID, err)
		}
		ack.AcceptedCount++
		inserted = append(inserted, item)
	}
	return ack, inserted, nil
}

func (s *MongoTelemetryStore) GetEventSummary(ctx context.Context, query application.EventSummaryQuery) (application.EventSummary, error) {
	items, err := s.findEvents(ctx, buildEventFilter(query), 0)
	if err != nil {
		return application.EventSummary{}, err
	}
	return summarizeEvents(items, query.EventType, query.EventName), nil
}

func (s *MongoTelemetryStore) GetEventDrilldown(ctx context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 50
	}
	items, err := s.findEvents(ctx, buildEventFilter(query), int64(limit))
	if err != nil {
		return application.EventDrilldown{}, err
	}
	return application.EventDrilldown{
		TotalCount: int64(len(items)),
		Items:      items,
	}, nil
}

func (s *MongoTelemetryStore) findEvents(ctx context.Context, filter bson.D, limit int64) ([]application.EventDrilldownItem, error) {
	opts := options.Find().SetSort(bson.D{{Key: "occurredAt", Value: -1}})
	if limit > 0 {
		opts.SetLimit(limit)
	}
	cursor, err := s.eventColl.Find(ctx, filter, opts)
	if err != nil {
		return nil, fmt.Errorf("find events: %w", err)
	}
	defer cursor.Close(ctx)
	items := make([]application.EventDrilldownItem, 0)
	for cursor.Next(ctx) {
		var item application.EventDrilldownItem
		if err := cursor.Decode(&item); err != nil {
			return nil, fmt.Errorf("decode event: %w", err)
		}
		items = append(items, item)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate events: %w", err)
	}
	return items, nil
}

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
	if query.Limit > 0 && len(items) > query.Limit {
		items = items[:query.Limit]
	}
	return application.EventDrilldown{
		TotalCount: int64(len(items)),
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

func normalizeEvent(raw application.EventRecordInput) application.EventDrilldownItem {
	now := nowRFC3339()
	occurredAt := strings.TrimSpace(raw.OccurredAt)
	if occurredAt == "" {
		occurredAt = now
	}
	clientSentAt := strings.TrimSpace(raw.ClientSentAt)
	return application.EventDrilldownItem{
		EventID:          strings.TrimSpace(raw.EventID),
		EventType:        firstNonEmpty(raw.EventType, "analytics"),
		EventName:        firstNonEmpty(raw.EventName, "unknown_event"),
		EventVersion:     firstNonEmpty(raw.EventVersion, "v1"),
		Priority:         firstNonEmpty(raw.Priority, "P1"),
		Producer:         firstNonEmpty(raw.Producer, "app"),
		Source:           strings.TrimSpace(raw.Source),
		UserIDHash:       strings.TrimSpace(raw.UserIDHash),
		SessionID:        strings.TrimSpace(raw.SessionID),
		PageVisitID:      strings.TrimSpace(raw.PageVisitID),
		SurfaceID:        strings.TrimSpace(raw.SurfaceID),
		RouteID:          strings.TrimSpace(raw.RouteID),
		OperationID:      strings.TrimSpace(raw.OperationID),
		RequestID:        strings.TrimSpace(raw.RequestID),
		TraceID:          strings.TrimSpace(raw.TraceID),
		PageName:         strings.TrimSpace(raw.PageName),
		TargetType:       strings.TrimSpace(raw.TargetType),
		TargetKey:        strings.TrimSpace(raw.TargetKey),
		EntityType:       strings.TrimSpace(raw.EntityType),
		EntityID:         strings.TrimSpace(raw.EntityID),
		ExperimentBucket: strings.TrimSpace(raw.ExperimentBucket),
		OccurredAt:       occurredAt,
		ClientSentAt:     clientSentAt,
		IngestedAt:       now,
		ErrorCode:        strings.TrimSpace(raw.ErrorCode),
		ErrorModule:      strings.TrimSpace(raw.ErrorModule),
		ErrorKind:        strings.TrimSpace(raw.ErrorKind),
		ErrorReason:      strings.TrimSpace(raw.ErrorReason),
		Origin:           strings.TrimSpace(raw.Origin),
		Nature:           strings.TrimSpace(raw.Nature),
		FailurePoint:     strings.TrimSpace(raw.FailurePoint),
		StackHash:        strings.TrimSpace(raw.StackHash),
		BusinessObject:   strings.TrimSpace(raw.BusinessObject),
		FunctionModule:   strings.TrimSpace(raw.FunctionModule),
		AppRuntimeEnv:    strings.TrimSpace(raw.AppRuntimeEnv),
		AppVersion:       strings.TrimSpace(raw.AppVersion),
		Platform:         strings.TrimSpace(raw.Platform),
		NetworkClass:     strings.TrimSpace(raw.NetworkClass),
		Payload:          cloneMap(raw.Payload),
		Metrics:          cloneMap(raw.Metrics),
	}
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

func buildEventFilter(query interface{}) bson.D {
	filter := bson.D{}
	appendString := func(key, value string) {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			filter = append(filter, bson.E{Key: key, Value: trimmed})
		}
	}
	switch q := query.(type) {
	case application.EventSummaryQuery:
		appendString("eventType", q.EventType)
		appendString("eventName", q.EventName)
		appendString("pageName", q.PageName)
		appendString("surfaceId", q.SurfaceID)
		appendString("routeId", q.RouteID)
		appendString("targetType", q.TargetType)
		appendString("targetKey", q.TargetKey)
		appendString("entityType", q.EntityType)
		appendString("entityId", q.EntityID)
		appendString("experimentBucket", q.ExperimentBucket)
		appendString("source", q.Source)
		appendTimeRange(&filter, q.From, q.To)
	case application.EventDrilldownQuery:
		appendString("eventType", q.EventType)
		appendString("eventName", q.EventName)
		appendString("pageName", q.PageName)
		appendString("surfaceId", q.SurfaceID)
		appendString("routeId", q.RouteID)
		appendString("targetType", q.TargetType)
		appendString("targetKey", q.TargetKey)
		appendString("entityType", q.EntityType)
		appendString("entityId", q.EntityID)
		appendString("experimentBucket", q.ExperimentBucket)
		appendString("source", q.Source)
		appendTimeRange(&filter, q.From, q.To)
	}
	return filter
}

func appendTimeRange(filter *bson.D, from, to time.Time) {
	rangeDoc := bson.D{}
	if !from.IsZero() {
		rangeDoc = append(rangeDoc, bson.E{Key: "$gte", Value: from.Format(time.RFC3339Nano)})
	}
	if !to.IsZero() {
		rangeDoc = append(rangeDoc, bson.E{Key: "$lte", Value: to.Format(time.RFC3339Nano)})
	}
	if len(rangeDoc) > 0 {
		*filter = append(*filter, bson.E{Key: "occurredAt", Value: rangeDoc})
	}
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
			if !ok {
				continue
			}
			if !withinTimeRange(item.OccurredAt, rangeDoc) {
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
		want, err := time.Parse(time.RFC3339Nano, fmt.Sprint(clause.Value))
		if err != nil {
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
		}
	}
	return true
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

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func cloneMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return nil
	}
	out := make(map[string]any, len(input))
	for key, value := range input {
		out[key] = value
	}
	return out
}

func visitKey(userID, targetType, targetKey string) string {
	return strings.Join([]string{userID, targetType, targetKey}, "|")
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}
