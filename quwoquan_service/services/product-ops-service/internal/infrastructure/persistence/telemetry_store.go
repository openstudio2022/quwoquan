package persistence

import (
	"context"
	"fmt"
	"sort"
	"strings"
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
		{Keys: bson.D{{Key: "sessionId", Value: 1}, {Key: "occurredAt", Value: -1}}, Options: options.Index().SetName("idx_event_session_time").SetSparse(true)},
		{Keys: bson.D{{Key: "expiresAt", Value: 1}}, Options: options.Index().SetName("ttl_event_expires_at").SetExpireAfterSeconds(0)},
		// 旧文档没有 expiresAt；保留 occurredAt TTL 作为迁移期兜底。新登录事件由
		// expiresAt 在 30 天删除，其余新事件仍按 90 天删除。
		{Keys: bson.D{{Key: "occurredAt", Value: 1}}, Options: options.Index().SetName("ttl_event_occurred_at").SetExpireAfterSeconds(90 * 24 * 60 * 60)},
	}
	visitIndexes := []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}}, Options: options.Index().SetName("uq_visit_user_target").SetUnique(true)},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_visit_user_target")},
		{Keys: bson.D{{Key: "targetType", Value: 1}, {Key: "targetKey", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_visit_target")},
		{Keys: bson.D{{Key: "sessionId", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_visit_session").SetSparse(true)},
		{Keys: bson.D{{Key: "timestamp", Value: 1}}, Options: options.Index().SetName("ttl_visit_timestamp").SetExpireAfterSeconds(180 * 24 * 60 * 60)},
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
	now := time.Now().UTC()
	filter := bson.D{
		{Key: "userId", Value: input.UserID},
		{Key: "targetType", Value: input.TargetType},
		{Key: "targetKey", Value: input.TargetKey},
	}
	setDoc := bson.D{
		{Key: "lastSeenAt", Value: formatEventTimestamp(now)},
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
		record, item, err := newMongoEventRecord(raw)
		if err != nil {
			return application.EventBatchAck{}, nil, fmt.Errorf("normalize event %q: %w", strings.TrimSpace(raw.EventID), err)
		}
		_, err = s.eventColl.InsertOne(ctx, record)
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
	filter := buildEventFilter(query)
	facets := bson.D{
		{Key: "overall", Value: mongo.Pipeline{
			bson.D{{Key: "$group", Value: bson.D{
				{Key: "_id", Value: nil},
				{Key: "totalCount", Value: bson.D{{Key: "$sum", Value: 1}}},
				{Key: "latestOccurredAt", Value: bson.D{{Key: "$max", Value: "$occurredAt"}}},
			}}},
		}},
	}
	for _, dimension := range eventSummaryDimensions {
		facets = append(facets, bson.E{Key: dimension, Value: dimensionCountPipeline(dimension)})
	}
	cursor, err := s.eventColl.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$match", Value: filter}},
		bson.D{{Key: "$facet", Value: facets}},
	})
	if err != nil {
		return application.EventSummary{}, fmt.Errorf("aggregate event summary: %w", err)
	}
	defer cursor.Close(ctx)
	out := application.EventSummary{
		EventType:         strings.TrimSpace(query.EventType),
		EventName:         strings.TrimSpace(query.EventName),
		DimensionCounters: map[string]map[string]int{},
	}
	if !cursor.Next(ctx) {
		if err := cursor.Err(); err != nil {
			return application.EventSummary{}, fmt.Errorf("iterate event summary: %w", err)
		}
		return out, nil
	}
	var result bson.M
	if err := cursor.Decode(&result); err != nil {
		return application.EventSummary{}, fmt.Errorf("decode event summary: %w", err)
	}
	if err := decodeEventSummaryResult(result, &out); err != nil {
		return application.EventSummary{}, err
	}
	return out, nil
}

func (s *MongoTelemetryStore) GetEventDrilldown(ctx context.Context, query application.EventDrilldownQuery) (application.EventDrilldown, error) {
	limit := query.Limit
	if limit <= 0 {
		limit = 50
	}
	filter := buildEventFilter(query)
	totalCount, err := s.eventColl.CountDocuments(ctx, filter)
	if err != nil {
		return application.EventDrilldown{}, fmt.Errorf("count event drilldown: %w", err)
	}
	items, err := s.findEvents(ctx, filter, int64(limit))
	if err != nil {
		return application.EventDrilldown{}, err
	}
	return application.EventDrilldown{
		TotalCount: totalCount,
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
		var record mongoEventRecord
		if err := cursor.Decode(&record); err != nil {
			return nil, fmt.Errorf("decode event: %w", err)
		}
		items = append(items, record.toApplication())
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate events: %w", err)
	}
	return items, nil
}

var eventSummaryDimensions = []string{
	"pageName",
	"surfaceId",
	"routeId",
	"experimentBucket",
	"targetKey",
	"entityId",
	"errorCode",
	"nature",
	"appRuntimeEnv",
	"source",
	"eventName",
}

func dimensionCountPipeline(field string) mongo.Pipeline {
	return mongo.Pipeline{
		bson.D{{Key: "$match", Value: bson.D{
			{Key: field, Value: bson.D{
				{Key: "$type", Value: "string"},
				{Key: "$ne", Value: ""},
			}},
		}}},
		bson.D{{Key: "$group", Value: bson.D{
			{Key: "_id", Value: "$" + field},
			{Key: "count", Value: bson.D{{Key: "$sum", Value: 1}}},
		}}},
	}
}

func decodeEventSummaryResult(result bson.M, out *application.EventSummary) error {
	overallRows, err := decodeSummaryRows(result["overall"])
	if err != nil {
		return fmt.Errorf("decode event summary overall: %w", err)
	}
	if len(overallRows) > 0 {
		if count, ok := numericInt64(overallRows[0]["totalCount"]); ok {
			out.TotalCount = count
		}
		if latest, ok := overallRows[0]["latestOccurredAt"].(bson.DateTime); ok {
			out.LatestOccurredAt = formatEventTimestamp(latest.Time())
		} else if latest, ok := overallRows[0]["latestOccurredAt"].(time.Time); ok {
			out.LatestOccurredAt = formatEventTimestamp(latest)
		}
	}
	for _, dimension := range eventSummaryDimensions {
		rows, decodeErr := decodeSummaryRows(result[dimension])
		if decodeErr != nil {
			return fmt.Errorf("decode event summary dimension %s: %w", dimension, decodeErr)
		}
		for _, row := range rows {
			value, _ := row["_id"].(string)
			count, ok := numericInt64(row["count"])
			if strings.TrimSpace(value) == "" || !ok {
				continue
			}
			if _, exists := out.DimensionCounters[dimension]; !exists {
				out.DimensionCounters[dimension] = map[string]int{}
			}
			out.DimensionCounters[dimension][value] = int(count)
		}
	}
	return nil
}

func decodeSummaryRows(value any) ([]bson.M, error) {
	raw, err := bson.Marshal(bson.M{"rows": value})
	if err != nil {
		return nil, err
	}
	var wrapper struct {
		Rows []bson.M `bson:"rows"`
	}
	if err := bson.Unmarshal(raw, &wrapper); err != nil {
		return nil, err
	}
	return wrapper.Rows, nil
}

func numericInt64(value any) (int64, bool) {
	switch typed := value.(type) {
	case int:
		return int64(typed), true
	case int32:
		return int64(typed), true
	case int64:
		return typed, true
	default:
		return 0, false
	}
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
		rangeDoc = append(rangeDoc, bson.E{Key: "$gte", Value: from.UTC()})
	}
	if !to.IsZero() {
		rangeDoc = append(rangeDoc, bson.E{Key: "$lte", Value: to.UTC()})
	}
	if len(rangeDoc) > 0 {
		*filter = append(*filter, bson.E{Key: "occurredAt", Value: rangeDoc})
	}
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

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339Nano)
}

var _ application.TelemetryStore = (*MongoTelemetryStore)(nil)
