package application

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/runtime/repository"
)

type VisitInput struct {
	UserID     string `json:"userId"`
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
	SessionID  string `json:"sessionId,omitempty"`
	Source     string `json:"source,omitempty"`
}

type VisitRecord struct {
	TargetType string `json:"targetType" bson:"targetType"`
	TargetKey  string `json:"targetKey" bson:"targetKey"`
	UserID     string `json:"userId" bson:"userId"`
	VisitCount int    `json:"visitCount" bson:"visitCount"`
	LastSeenAt string `json:"lastSeenAt,omitempty" bson:"lastSeenAt,omitempty"`
	SessionID  string `json:"sessionId,omitempty" bson:"sessionId,omitempty"`
	Source     string `json:"source,omitempty" bson:"source,omitempty"`
}

type VisitStatsQuery struct {
	TargetType string
	TargetKey  string
}

type VisitStats struct {
	TotalVisits int           `json:"totalVisits"`
	Items       []VisitRecord `json:"items"`
}

type EventRecordInput struct {
	EventID          string         `json:"eventId"`
	EventType        string         `json:"eventType"`
	EventName        string         `json:"eventName"`
	EventVersion     string         `json:"eventVersion"`
	Priority         string         `json:"priority"`
	Producer         string         `json:"producer"`
	Source           string         `json:"source,omitempty"`
	UserIDHash       string         `json:"userIdHash,omitempty"`
	SessionID        string         `json:"sessionId,omitempty"`
	JourneyID        string         `json:"journeyId,omitempty"`
	PageVisitID      string         `json:"pageVisitId,omitempty"`
	SurfaceID        string         `json:"surfaceId,omitempty"`
	RouteID          string         `json:"routeId,omitempty"`
	OperationID      string         `json:"operationId,omitempty"`
	RequestID        string         `json:"requestId,omitempty"`
	PageName         string         `json:"pageName,omitempty"`
	TargetType       string         `json:"targetType,omitempty"`
	TargetKey        string         `json:"targetKey,omitempty"`
	EntityType       string         `json:"entityType,omitempty"`
	EntityID         string         `json:"entityId,omitempty"`
	ExperimentBucket string         `json:"experimentBucket,omitempty"`
	OccurredAt       string         `json:"occurredAt"`
	ClientSentAt     string         `json:"clientSentAt,omitempty"`
	Payload          map[string]any `json:"payload,omitempty"`
	Metrics          map[string]any `json:"metrics,omitempty"`
}

type EventBatchAck struct {
	AcceptedCount  int `json:"acceptedCount"`
	DuplicateCount int `json:"duplicateCount"`
}

type EventSummaryQuery struct {
	EventType        string
	EventName        string
	PageName         string
	SurfaceID        string
	RouteID          string
	TargetType       string
	TargetKey        string
	EntityType       string
	EntityID         string
	ExperimentBucket string
	Source           string
	From             time.Time
	To               time.Time
}

type EventSummary struct {
	TotalCount        int64                     `json:"totalCount"`
	EventType         string                    `json:"eventType,omitempty"`
	EventName         string                    `json:"eventName,omitempty"`
	LatestOccurredAt  string                    `json:"latestOccurredAt,omitempty"`
	DimensionCounters map[string]map[string]int `json:"dimensions"`
}

type EventDrilldownQuery struct {
	EventType        string
	EventName        string
	PageName         string
	SurfaceID        string
	RouteID          string
	TargetType       string
	TargetKey        string
	EntityType       string
	EntityID         string
	ExperimentBucket string
	Source           string
	From             time.Time
	To               time.Time
	Limit            int
}

type EventDrilldownItem struct {
	EventID          string         `json:"eventId" bson:"eventId"`
	EventType        string         `json:"eventType" bson:"eventType"`
	EventName        string         `json:"eventName" bson:"eventName"`
	EventVersion     string         `json:"eventVersion" bson:"eventVersion"`
	Priority         string         `json:"priority" bson:"priority"`
	Producer         string         `json:"producer" bson:"producer"`
	Source           string         `json:"source,omitempty" bson:"source,omitempty"`
	UserIDHash       string         `json:"userIdHash,omitempty" bson:"userIdHash,omitempty"`
	SessionID        string         `json:"sessionId,omitempty" bson:"sessionId,omitempty"`
	JourneyID        string         `json:"journeyId,omitempty" bson:"journeyId,omitempty"`
	PageVisitID      string         `json:"pageVisitId,omitempty" bson:"pageVisitId,omitempty"`
	SurfaceID        string         `json:"surfaceId,omitempty" bson:"surfaceId,omitempty"`
	RouteID          string         `json:"routeId,omitempty" bson:"routeId,omitempty"`
	OperationID      string         `json:"operationId,omitempty" bson:"operationId,omitempty"`
	RequestID        string         `json:"requestId,omitempty" bson:"requestId,omitempty"`
	PageName         string         `json:"pageName,omitempty" bson:"pageName,omitempty"`
	TargetType       string         `json:"targetType,omitempty" bson:"targetType,omitempty"`
	TargetKey        string         `json:"targetKey,omitempty" bson:"targetKey,omitempty"`
	EntityType       string         `json:"entityType,omitempty" bson:"entityType,omitempty"`
	EntityID         string         `json:"entityId,omitempty" bson:"entityId,omitempty"`
	ExperimentBucket string         `json:"experimentBucket,omitempty" bson:"experimentBucket,omitempty"`
	OccurredAt       string         `json:"occurredAt" bson:"occurredAt"`
	ClientSentAt     string         `json:"clientSentAt,omitempty" bson:"clientSentAt,omitempty"`
	IngestedAt       string         `json:"ingestedAt" bson:"ingestedAt"`
	Payload          map[string]any `json:"payload,omitempty" bson:"payload,omitempty"`
	Metrics          map[string]any `json:"metrics,omitempty" bson:"metrics,omitempty"`
}

type EventDrilldown struct {
	TotalCount int64                `json:"totalCount"`
	Items      []EventDrilldownItem `json:"items"`
}

type TelemetryStore interface {
	RecordVisit(ctx context.Context, input VisitInput) (VisitRecord, error)
	GetVisitStats(ctx context.Context, query VisitStatsQuery) (VisitStats, error)
	ReportEventBatch(ctx context.Context, events []EventRecordInput) (EventBatchAck, []EventDrilldownItem, error)
	GetEventSummary(ctx context.Context, query EventSummaryQuery) (EventSummary, error)
	GetEventDrilldown(ctx context.Context, query EventDrilldownQuery) (EventDrilldown, error)
}

type TelemetryService struct {
	store     TelemetryStore
	publisher repository.EventPublisher
}

func NewTelemetryService(store TelemetryStore, publisher repository.EventPublisher) *TelemetryService {
	return &TelemetryService{store: store, publisher: publisher}
}

func (s *TelemetryService) RecordVisit(ctx context.Context, input VisitInput) (VisitRecord, error) {
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.TargetKey = strings.TrimSpace(input.TargetKey)
	input.UserID = strings.TrimSpace(input.UserID)
	if input.UserID == "" {
		input.UserID = "anonymous"
	}
	return s.store.RecordVisit(ctx, input)
}

func (s *TelemetryService) GetVisitStats(ctx context.Context, query VisitStatsQuery) (VisitStats, error) {
	return s.store.GetVisitStats(ctx, query)
}

func (s *TelemetryService) ReportEventBatch(ctx context.Context, events []EventRecordInput) (EventBatchAck, error) {
	ack, inserted, err := s.store.ReportEventBatch(ctx, events)
	if err != nil {
		return EventBatchAck{}, err
	}
	if s.publisher != nil {
		for _, item := range inserted {
			payload := map[string]any{
				"eventId":          item.EventID,
				"eventType":        item.EventType,
				"eventName":        item.EventName,
				"pageName":         item.PageName,
				"surfaceId":        item.SurfaceID,
				"routeId":          item.RouteID,
				"operationId":      item.OperationID,
				"targetType":       item.TargetType,
				"targetKey":        item.TargetKey,
				"entityType":       item.EntityType,
				"entityId":         item.EntityID,
				"experimentBucket": item.ExperimentBucket,
				"occurredAt":       item.OccurredAt,
				"source":           item.Source,
			}
			_ = s.publisher.Publish(ctx, repository.DomainEvent{
				Type:          "EventBatchReported",
				AggregateType: "EventRecord",
				AggregateID:   item.EventID,
				Payload:       payload,
				OccurredAt:    item.OccurredAt,
			})
		}
	}
	return ack, nil
}

func (s *TelemetryService) GetEventSummary(ctx context.Context, query EventSummaryQuery) (EventSummary, error) {
	return s.store.GetEventSummary(ctx, query)
}

func (s *TelemetryService) GetEventDrilldown(ctx context.Context, query EventDrilldownQuery) (EventDrilldown, error) {
	if query.Limit <= 0 {
		query.Limit = 50
	}
	return s.store.GetEventDrilldown(ctx, query)
}
