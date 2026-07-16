package persistence

import (
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

type mongoEventRecord struct {
	EventID          string         `bson:"eventId"`
	EventType        string         `bson:"eventType"`
	EventName        string         `bson:"eventName"`
	EventVersion     string         `bson:"eventVersion"`
	Priority         string         `bson:"priority"`
	Producer         string         `bson:"producer"`
	Source           string         `bson:"source,omitempty"`
	UserIDHash       string         `bson:"userIdHash,omitempty"`
	SessionID        string         `bson:"sessionId,omitempty"`
	PageVisitID      string         `bson:"pageVisitId,omitempty"`
	SurfaceID        string         `bson:"surfaceId,omitempty"`
	RouteID          string         `bson:"routeId,omitempty"`
	OperationID      string         `bson:"operationId,omitempty"`
	RequestID        string         `bson:"requestId,omitempty"`
	TraceID          string         `bson:"traceId,omitempty"`
	PageName         string         `bson:"pageName,omitempty"`
	TargetType       string         `bson:"targetType,omitempty"`
	TargetKey        string         `bson:"targetKey,omitempty"`
	EntityType       string         `bson:"entityType,omitempty"`
	EntityID         string         `bson:"entityId,omitempty"`
	ExperimentBucket string         `bson:"experimentBucket,omitempty"`
	OccurredAt       time.Time      `bson:"occurredAt"`
	ExpiresAt        time.Time      `bson:"expiresAt"`
	ClientSentAt     *time.Time     `bson:"clientSentAt,omitempty"`
	IngestedAt       time.Time      `bson:"ingestedAt"`
	ErrorCode        string         `bson:"errorCode,omitempty"`
	ErrorModule      string         `bson:"errorModule,omitempty"`
	ErrorKind        string         `bson:"errorKind,omitempty"`
	ErrorReason      string         `bson:"errorReason,omitempty"`
	Origin           string         `bson:"origin,omitempty"`
	Nature           string         `bson:"nature,omitempty"`
	FailurePoint     string         `bson:"failurePoint,omitempty"`
	StackHash        string         `bson:"stackHash,omitempty"`
	BusinessObject   string         `bson:"businessObject,omitempty"`
	FunctionModule   string         `bson:"functionModule,omitempty"`
	AppRuntimeEnv    string         `bson:"appRuntimeEnv,omitempty"`
	AppVersion       string         `bson:"appVersion,omitempty"`
	Platform         string         `bson:"platform,omitempty"`
	NetworkClass     string         `bson:"networkClass,omitempty"`
	Payload          map[string]any `bson:"payload,omitempty"`
	Metrics          map[string]any `bson:"metrics,omitempty"`
}

func newMongoEventRecord(raw application.EventRecordInput) (mongoEventRecord, application.EventDrilldownItem, error) {
	item := normalizeEvent(raw)
	occurredAt, err := parseEventTimestamp("occurredAt", item.OccurredAt)
	if err != nil {
		return mongoEventRecord{}, application.EventDrilldownItem{}, err
	}
	ingestedAt, err := parseEventTimestamp("ingestedAt", item.IngestedAt)
	if err != nil {
		return mongoEventRecord{}, application.EventDrilldownItem{}, err
	}
	var clientSentAt *time.Time
	if strings.TrimSpace(item.ClientSentAt) != "" {
		parsed, parseErr := parseEventTimestamp("clientSentAt", item.ClientSentAt)
		if parseErr != nil {
			return mongoEventRecord{}, application.EventDrilldownItem{}, parseErr
		}
		clientSentAt = &parsed
		item.ClientSentAt = formatEventTimestamp(parsed)
	}
	item.OccurredAt = formatEventTimestamp(occurredAt)
	item.IngestedAt = formatEventTimestamp(ingestedAt)
	retention := 90 * 24 * time.Hour
	if strings.HasPrefix(strings.ToLower(strings.TrimSpace(item.EventName)), "login_") {
		retention = 30 * 24 * time.Hour
	}
	return mongoEventRecord{
		EventID:          item.EventID,
		EventType:        item.EventType,
		EventName:        item.EventName,
		EventVersion:     item.EventVersion,
		Priority:         item.Priority,
		Producer:         item.Producer,
		Source:           item.Source,
		UserIDHash:       item.UserIDHash,
		SessionID:        item.SessionID,
		PageVisitID:      item.PageVisitID,
		SurfaceID:        item.SurfaceID,
		RouteID:          item.RouteID,
		OperationID:      item.OperationID,
		RequestID:        item.RequestID,
		TraceID:          item.TraceID,
		PageName:         item.PageName,
		TargetType:       item.TargetType,
		TargetKey:        item.TargetKey,
		EntityType:       item.EntityType,
		EntityID:         item.EntityID,
		ExperimentBucket: item.ExperimentBucket,
		OccurredAt:       occurredAt,
		ExpiresAt:        occurredAt.Add(retention),
		ClientSentAt:     clientSentAt,
		IngestedAt:       ingestedAt,
		ErrorCode:        item.ErrorCode,
		ErrorModule:      item.ErrorModule,
		ErrorKind:        item.ErrorKind,
		ErrorReason:      item.ErrorReason,
		Origin:           item.Origin,
		Nature:           item.Nature,
		FailurePoint:     item.FailurePoint,
		StackHash:        item.StackHash,
		BusinessObject:   item.BusinessObject,
		FunctionModule:   item.FunctionModule,
		AppRuntimeEnv:    item.AppRuntimeEnv,
		AppVersion:       item.AppVersion,
		Platform:         item.Platform,
		NetworkClass:     item.NetworkClass,
		Payload:          item.Payload,
		Metrics:          item.Metrics,
	}, item, nil
}

func (record mongoEventRecord) toApplication() application.EventDrilldownItem {
	clientSentAt := ""
	if record.ClientSentAt != nil {
		clientSentAt = formatEventTimestamp(*record.ClientSentAt)
	}
	return application.EventDrilldownItem{
		EventID:          record.EventID,
		EventType:        record.EventType,
		EventName:        record.EventName,
		EventVersion:     record.EventVersion,
		Priority:         record.Priority,
		Producer:         record.Producer,
		Source:           record.Source,
		UserIDHash:       record.UserIDHash,
		SessionID:        record.SessionID,
		PageVisitID:      record.PageVisitID,
		SurfaceID:        record.SurfaceID,
		RouteID:          record.RouteID,
		OperationID:      record.OperationID,
		RequestID:        record.RequestID,
		TraceID:          record.TraceID,
		PageName:         record.PageName,
		TargetType:       record.TargetType,
		TargetKey:        record.TargetKey,
		EntityType:       record.EntityType,
		EntityID:         record.EntityID,
		ExperimentBucket: record.ExperimentBucket,
		OccurredAt:       formatEventTimestamp(record.OccurredAt),
		ClientSentAt:     clientSentAt,
		IngestedAt:       formatEventTimestamp(record.IngestedAt),
		ErrorCode:        record.ErrorCode,
		ErrorModule:      record.ErrorModule,
		ErrorKind:        record.ErrorKind,
		ErrorReason:      record.ErrorReason,
		Origin:           record.Origin,
		Nature:           record.Nature,
		FailurePoint:     record.FailurePoint,
		StackHash:        record.StackHash,
		BusinessObject:   record.BusinessObject,
		FunctionModule:   record.FunctionModule,
		AppRuntimeEnv:    record.AppRuntimeEnv,
		AppVersion:       record.AppVersion,
		Platform:         record.Platform,
		NetworkClass:     record.NetworkClass,
		Payload:          record.Payload,
		Metrics:          record.Metrics,
	}
}

func parseEventTimestamp(field, raw string) (time.Time, error) {
	parsed, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(raw))
	if err != nil {
		return time.Time{}, fmt.Errorf("%s must be RFC3339: %w", field, err)
	}
	return parsed.UTC(), nil
}

func formatEventTimestamp(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.UTC().Format(time.RFC3339Nano)
}
