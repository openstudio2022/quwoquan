package application

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"quwoquan_service/services/product-ops-service/internal/generated"
)

var (
	ErrInvalidEventBatch = errors.New("invalid event batch")
	ErrBatchInProgress   = errors.New("event batch is still in progress")
	ErrInvalidEventQuery = errors.New("invalid event query")
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

type VisitStatsQuery struct{ TargetType, TargetKey string }
type VisitStats struct {
	TotalVisits int           `json:"totalVisits"`
	Items       []VisitRecord `json:"items"`
}

// EventRecordInput 是 /ops/events 唯一 wire shape。九个公共字段之外只允许
// event_catalog.yaml 中登记的强类型扩展；JSON decoder 会拒绝任何未知字段。
type EventRecordInput struct {
	LogType              string   `json:"logType"`
	EventType            string   `json:"eventType"`
	SessionID            string   `json:"sessionId"`
	PageName             string   `json:"pageName"`
	OccurredAt           string   `json:"occurredAt"`
	DeviceManufacturer   string   `json:"deviceManufacturer"`
	DeviceModel          string   `json:"deviceModel"`
	AppVersion           string   `json:"appVersion"`
	NetworkClass         string   `json:"networkClass"`
	DurationMS           *int     `json:"durationMs,omitempty"`
	Result               *string  `json:"result,omitempty"`
	FailReasonCode       *string  `json:"failReasonCode,omitempty"`
	ErrorCode            *string  `json:"errorCode,omitempty"`
	OperationID          *string  `json:"operationId,omitempty"`
	HTTPStatus           *int     `json:"httpStatus,omitempty"`
	CallStack            []string `json:"callStack,omitempty"`
	TClickToFirstFrameMS *int     `json:"tClickToFirstFrameMs,omitempty"`
	TFirstFrameToShellMS *int     `json:"tFirstFrameToShellMs,omitempty"`
	TShellToContentMS    *int     `json:"tShellToContentMs,omitempty"`
	TClickToContentMS    *int     `json:"tClickToContentMs,omitempty"`
	HasError             *bool    `json:"hasError,omitempty"`
	Journey              *string  `json:"journey,omitempty"`
	Action               *string  `json:"action,omitempty"`
	ReadyMS              *int     `json:"readyMs,omitempty"`
	TTFFMS               *int     `json:"ttffMs,omitempty"`
	RebufferCount        *int     `json:"rebufferCount,omitempty"`
	RebufferMS           *int     `json:"rebufferMs,omitempty"`
	SeekCount            *int     `json:"seekCount,omitempty"`
	DeclaredDurationMS   *int     `json:"declaredDurationMs,omitempty"`
	ObservedDurationMS   *int     `json:"observedDurationMs,omitempty"`
	DurationMismatch     *bool    `json:"durationMismatch,omitempty"`
	PlaybackMode         *string  `json:"playbackMode,omitempty"`
}

type EventRecord struct {
	EventRecordInput
	BatchKey   string    `json:"-"`
	BatchIndex int       `json:"-"`
	IngestedAt time.Time `json:"-"`
}

type EventBatchAck struct {
	AcceptedCount  int  `json:"acceptedCount"`
	DuplicateBatch bool `json:"duplicateBatch"`
}

type EventSummaryQuery struct {
	LogType, EventType, PageName, AppVersion, NetworkClass, ErrorCode string
	From, To                                                          time.Time
}

type EventSummary struct {
	TotalCount        int64                     `json:"totalCount"`
	SessionCount      int64                     `json:"sessionCount"`
	DimensionCounters map[string]map[string]int `json:"dimensions"`
	Source            string                    `json:"source"`
	Freshness         string                    `json:"freshness"`
	ActualFrom        string                    `json:"actualFrom"`
	ActualTo          string                    `json:"actualTo"`
}

type EventDrilldownQuery struct {
	LogType, EventType, PageName, AppVersion, NetworkClass, ErrorCode, SessionID string
	From, To                                                                     time.Time
	Limit                                                                        int
	RevealSession                                                                bool
}

type EventDrilldownItem struct {
	RowKey               string   `json:"rowKey"`
	LogType              string   `json:"logType"`
	EventType            string   `json:"eventType"`
	SessionID            string   `json:"sessionId"`
	PageName             string   `json:"pageName"`
	OccurredAt           string   `json:"occurredAt"`
	DeviceManufacturer   string   `json:"deviceManufacturer"`
	DeviceModel          string   `json:"deviceModel"`
	AppVersion           string   `json:"appVersion"`
	NetworkClass         string   `json:"networkClass"`
	DurationMS           *int     `json:"durationMs,omitempty"`
	Result               *string  `json:"result,omitempty"`
	FailReasonCode       *string  `json:"failReasonCode,omitempty"`
	ErrorCode            *string  `json:"errorCode,omitempty"`
	OperationID          *string  `json:"operationId,omitempty"`
	HTTPStatus           *int     `json:"httpStatus,omitempty"`
	CallStack            []string `json:"callStack,omitempty"`
	TClickToFirstFrameMS *int     `json:"tClickToFirstFrameMs,omitempty"`
	TFirstFrameToShellMS *int     `json:"tFirstFrameToShellMs,omitempty"`
	TShellToContentMS    *int     `json:"tShellToContentMs,omitempty"`
	TClickToContentMS    *int     `json:"tClickToContentMs,omitempty"`
	HasError             *bool    `json:"hasError,omitempty"`
	Journey              *string  `json:"journey,omitempty"`
	Action               *string  `json:"action,omitempty"`
	ReadyMS              *int     `json:"readyMs,omitempty"`
	TTFFMS               *int     `json:"ttffMs,omitempty"`
	RebufferCount        *int     `json:"rebufferCount,omitempty"`
	RebufferMS           *int     `json:"rebufferMs,omitempty"`
	SeekCount            *int     `json:"seekCount,omitempty"`
	DeclaredDurationMS   *int     `json:"declaredDurationMs,omitempty"`
	ObservedDurationMS   *int     `json:"observedDurationMs,omitempty"`
	DurationMismatch     *bool    `json:"durationMismatch,omitempty"`
	PlaybackMode         *string  `json:"playbackMode,omitempty"`
	IngestedAt           string   `json:"ingestedAt"`
}

type EventDrilldown struct {
	TotalCount int64                `json:"totalCount"`
	Items      []EventDrilldownItem `json:"items"`
	Source     string               `json:"source"`
	Freshness  string               `json:"freshness"`
	ActualFrom string               `json:"actualFrom"`
	ActualTo   string               `json:"actualTo"`
}

// EventTelemetrySnapshot 是 Portal 聚合卡片的服务端组合视图。它不引入新的
// 存储或 wire contract，只把闭合小时 summary 与最多三天 raw drilldown 合并。
type EventTelemetrySnapshot struct {
	Summary   EventSummary
	Drilldown EventDrilldown
}

type StartupDiagnosticRecord struct {
	EventID, AttemptID, Phase, Outcome, OccurredAt, Platform, RuntimeEnv                  string
	AppVersion, NetworkClass, RecoverySurface, FailureCode, FailureSource, DeadlineOrigin string
	Sequence, PhaseDurationMS, ElapsedMS                                                  int
}

type VisitTelemetryStore interface {
	RecordVisit(context.Context, VisitInput) (VisitRecord, error)
	GetVisitStats(context.Context, VisitStatsQuery) (VisitStats, error)
}

type EventLogStore interface {
	PutEventBatch(context.Context, string, []EventRecord) error
	HasEventBatch(context.Context, string, int) (bool, error)
	GetEventSummary(context.Context, EventSummaryQuery) (EventSummary, error)
	GetEventDrilldown(context.Context, EventDrilldownQuery) (EventDrilldown, error)
	PutStartupDiagnostics(context.Context, string, []StartupDiagnosticRecord) error
	HasStartupDiagnosticBatch(context.Context, string, int) (bool, error)
}

type EventBatchLedger interface {
	Begin(context.Context, string, int) (BatchLedgerState, error)
	MarkAccepted(context.Context, string, int) error
}

type BatchLedgerState string

const (
	BatchLedgerNew      BatchLedgerState = "new"
	BatchLedgerPending  BatchLedgerState = "pending"
	BatchLedgerAccepted BatchLedgerState = "accepted"
)

type TelemetryStore interface {
	VisitTelemetryStore
	EventLogStore
	EventBatchLedger
}

type TelemetryService struct {
	visits VisitTelemetryStore
	events EventLogStore
	ledger EventBatchLedger
	now    func() time.Time
}

func NewTelemetryService(store TelemetryStore, _ any) *TelemetryService {
	return NewTelemetryServiceWithStores(store, store, store)
}

func NewTelemetryServiceWithStores(visits VisitTelemetryStore, events EventLogStore, ledger EventBatchLedger) *TelemetryService {
	return &TelemetryService{visits: visits, events: events, ledger: ledger, now: time.Now}
}

func (s *TelemetryService) RecordVisit(ctx context.Context, input VisitInput) (VisitRecord, error) {
	input.TargetType = strings.TrimSpace(input.TargetType)
	input.TargetKey = strings.TrimSpace(input.TargetKey)
	input.UserID = strings.TrimSpace(input.UserID)
	if input.UserID == "" {
		input.UserID = "anonymous"
	}
	return s.visits.RecordVisit(ctx, input)
}

func (s *TelemetryService) GetVisitStats(ctx context.Context, query VisitStatsQuery) (VisitStats, error) {
	return s.visits.GetVisitStats(ctx, query)
}

func (s *TelemetryService) ReportEventBatch(ctx context.Context, batchKey string, inputs []EventRecordInput) (EventBatchAck, error) {
	if len(inputs) == 0 || len(inputs) > 50 || len(batchKey) != 64 {
		return EventBatchAck{}, ErrInvalidEventBatch
	}
	now := s.now().UTC()
	records := make([]EventRecord, len(inputs))
	for index, input := range inputs {
		if err := validateEvent(input, now); err != nil {
			return EventBatchAck{}, fmt.Errorf("%w: event[%d]: %v", ErrInvalidEventBatch, index, err)
		}
		occurredAt, _ := time.Parse(time.RFC3339Nano, input.OccurredAt)
		input.OccurredAt = occurredAt.UTC().Format(time.RFC3339Nano)
		records[index] = EventRecord{EventRecordInput: input, BatchKey: batchKey, BatchIndex: index, IngestedAt: now}
	}
	state, err := s.ledger.Begin(ctx, batchKey, len(records))
	if err != nil {
		return EventBatchAck{}, err
	}
	if state == BatchLedgerAccepted {
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if state == BatchLedgerPending {
		confirmed, confirmErr := s.events.HasEventBatch(ctx, batchKey, len(records))
		if confirmErr != nil {
			return EventBatchAck{}, confirmErr
		}
		if !confirmed {
			return EventBatchAck{}, ErrBatchInProgress
		}
		if err := s.ledger.MarkAccepted(ctx, batchKey, len(records)); err != nil {
			return EventBatchAck{}, err
		}
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if err := s.events.PutEventBatch(ctx, batchKey, records); err != nil {
		confirmed, confirmErr := s.events.HasEventBatch(ctx, batchKey, len(records))
		if confirmErr != nil || !confirmed {
			return EventBatchAck{}, err
		}
	}
	if err := s.ledger.MarkAccepted(ctx, batchKey, len(records)); err != nil {
		return EventBatchAck{}, err
	}
	return EventBatchAck{AcceptedCount: len(records)}, nil
}

func (s *TelemetryService) ReportStartupDiagnostics(ctx context.Context, proof string, records []StartupDiagnosticRecord) (EventBatchAck, error) {
	if len(records) == 0 || len(records) > 32 || strings.TrimSpace(proof) == "" {
		return EventBatchAck{}, ErrInvalidEventBatch
	}
	digest := sha256.Sum256([]byte("startup:" + proof))
	batchKey := hex.EncodeToString(digest[:])
	state, err := s.ledger.Begin(ctx, batchKey, len(records))
	if err != nil {
		return EventBatchAck{}, err
	}
	if state == BatchLedgerAccepted {
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if state == BatchLedgerPending {
		confirmed, confirmErr := s.events.HasStartupDiagnosticBatch(ctx, batchKey, len(records))
		if confirmErr != nil {
			return EventBatchAck{}, confirmErr
		}
		if !confirmed {
			return EventBatchAck{}, ErrBatchInProgress
		}
		if err := s.ledger.MarkAccepted(ctx, batchKey, len(records)); err != nil {
			return EventBatchAck{}, err
		}
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if err := s.events.PutStartupDiagnostics(ctx, batchKey, records); err != nil {
		confirmed, confirmErr := s.events.HasStartupDiagnosticBatch(ctx, batchKey, len(records))
		if confirmErr != nil || !confirmed {
			return EventBatchAck{}, err
		}
	}
	if err := s.ledger.MarkAccepted(ctx, batchKey, len(records)); err != nil {
		return EventBatchAck{}, err
	}
	return EventBatchAck{AcceptedCount: len(records)}, nil
}

func (s *TelemetryService) GetEventSummary(ctx context.Context, query EventSummaryQuery) (EventSummary, error) {
	if err := normalizeSummaryQuery(&query, s.now().UTC()); err != nil {
		return EventSummary{}, err
	}
	if err := validateQueryFilters(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode); err != nil {
		return EventSummary{}, err
	}
	return s.events.GetEventSummary(ctx, query)
}

func (s *TelemetryService) GetEventDrilldown(ctx context.Context, query EventDrilldownQuery) (EventDrilldown, error) {
	now := s.now().UTC()
	if query.From.IsZero() || query.To.IsZero() || !query.From.Before(query.To) || query.To.Sub(query.From) > 72*time.Hour {
		return EventDrilldown{}, ErrInvalidEventQuery
	}
	if query.To.After(now.Add(5*time.Minute)) || query.From.Before(now.Add(-72*time.Hour)) {
		return EventDrilldown{}, ErrInvalidEventQuery
	}
	if query.Limit <= 0 {
		query.Limit = 50
	}
	if query.Limit > 100 {
		return EventDrilldown{}, ErrInvalidEventQuery
	}
	if err := validateQueryFilters(query.LogType, query.EventType, query.PageName, query.AppVersion, query.NetworkClass, query.ErrorCode); err != nil {
		return EventDrilldown{}, err
	}
	if query.SessionID != "" {
		if err := validateSessionID(query.SessionID); err != nil {
			return EventDrilldown{}, ErrInvalidEventQuery
		}
	}
	return s.events.GetEventDrilldown(ctx, query)
}

func (s *TelemetryService) SnapshotEvents(
	ctx context.Context,
	query EventSummaryQuery,
	limit int,
) (EventTelemetrySnapshot, error) {
	if err := normalizeSummaryQuery(&query, s.now().UTC()); err != nil {
		return EventTelemetrySnapshot{}, err
	}
	summary, err := s.events.GetEventSummary(ctx, query)
	if err != nil {
		return EventTelemetrySnapshot{}, err
	}
	drilldownFrom := query.From
	oldestRaw := s.now().UTC().Add(-72 * time.Hour)
	if drilldownFrom.Before(oldestRaw) {
		drilldownFrom = oldestRaw
	}
	drilldownLimit := limit
	if drilldownLimit <= 0 || drilldownLimit > 100 {
		drilldownLimit = 100
	}
	drilldown, err := s.GetEventDrilldown(ctx, EventDrilldownQuery{
		LogType:      query.LogType,
		EventType:    query.EventType,
		PageName:     query.PageName,
		AppVersion:   query.AppVersion,
		NetworkClass: query.NetworkClass,
		ErrorCode:    query.ErrorCode,
		From:         drilldownFrom,
		To:           query.To,
		Limit:        drilldownLimit,
	})
	if err != nil {
		return EventTelemetrySnapshot{}, err
	}
	return EventTelemetrySnapshot{Summary: summary, Drilldown: drilldown}, nil
}

func validateEvent(input EventRecordInput, now time.Time) error {
	definition, ok := generated.EventCatalog[input.EventType]
	if !ok || input.LogType != definition.LogType {
		return fmt.Errorf("unknown eventType/logType")
	}
	if _, ok := generated.EventNetworkClasses[input.NetworkClass]; !ok {
		return fmt.Errorf("unknown networkClass")
	}
	if _, ok := generated.AppPageNames[input.PageName]; !ok {
		return fmt.Errorf("unknown pageName")
	}
	for name, value := range map[string]string{
		"sessionId": input.SessionID, "pageName": input.PageName, "occurredAt": input.OccurredAt,
		"deviceManufacturer": input.DeviceManufacturer, "deviceModel": input.DeviceModel,
		"appVersion": input.AppVersion, "networkClass": input.NetworkClass,
	} {
		if strings.TrimSpace(value) == "" || !utf8.ValidString(value) || utf8.RuneCountInString(value) > 256 {
			return fmt.Errorf("%s is invalid", name)
		}
	}
	if err := validateSessionID(input.SessionID); err != nil {
		return err
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, input.OccurredAt)
	if err != nil || occurredAt.Before(now.Add(-72*time.Hour)) || occurredAt.After(now.Add(5*time.Minute)) {
		return fmt.Errorf("occurredAt outside accepted window")
	}
	extensions := input.extensions()
	for required := range definition.RequiredExtensions {
		if _, ok := extensions[required]; !ok {
			return fmt.Errorf("missing extension %s", required)
		}
	}
	for name, value := range extensions {
		if _, ok := definition.RequiredExtensions[name]; !ok {
			if _, ok := definition.OptionalExtensions[name]; !ok {
				return fmt.Errorf("unknown extension %s", name)
			}
		}
		if err := validateExtension(name, value); err != nil {
			return err
		}
	}
	return nil
}

func (input EventRecordInput) extensions() map[string]any {
	out := map[string]any{}
	if input.DurationMS != nil {
		out["durationMs"] = *input.DurationMS
	}
	if input.Result != nil {
		out["result"] = *input.Result
	}
	if input.FailReasonCode != nil {
		out["failReasonCode"] = *input.FailReasonCode
	}
	if input.ErrorCode != nil {
		out["errorCode"] = *input.ErrorCode
	}
	if input.OperationID != nil {
		out["operationId"] = *input.OperationID
	}
	if input.HTTPStatus != nil {
		out["httpStatus"] = *input.HTTPStatus
	}
	if input.CallStack != nil {
		out["callStack"] = input.CallStack
	}
	if input.TClickToFirstFrameMS != nil {
		out["tClickToFirstFrameMs"] = *input.TClickToFirstFrameMS
	}
	if input.TFirstFrameToShellMS != nil {
		out["tFirstFrameToShellMs"] = *input.TFirstFrameToShellMS
	}
	if input.TShellToContentMS != nil {
		out["tShellToContentMs"] = *input.TShellToContentMS
	}
	if input.TClickToContentMS != nil {
		out["tClickToContentMs"] = *input.TClickToContentMS
	}
	if input.HasError != nil {
		out["hasError"] = *input.HasError
	}
	if input.Journey != nil {
		out["journey"] = *input.Journey
	}
	if input.Action != nil {
		out["action"] = *input.Action
	}
	if input.ReadyMS != nil {
		out["readyMs"] = *input.ReadyMS
	}
	if input.TTFFMS != nil {
		out["ttffMs"] = *input.TTFFMS
	}
	if input.RebufferCount != nil {
		out["rebufferCount"] = *input.RebufferCount
	}
	if input.RebufferMS != nil {
		out["rebufferMs"] = *input.RebufferMS
	}
	if input.SeekCount != nil {
		out["seekCount"] = *input.SeekCount
	}
	if input.DeclaredDurationMS != nil {
		out["declaredDurationMs"] = *input.DeclaredDurationMS
	}
	if input.ObservedDurationMS != nil {
		out["observedDurationMs"] = *input.ObservedDurationMS
	}
	if input.DurationMismatch != nil {
		out["durationMismatch"] = *input.DurationMismatch
	}
	if input.PlaybackMode != nil {
		out["playbackMode"] = *input.PlaybackMode
	}
	return out
}

func validateExtension(name string, value any) error {
	definition := generated.EventExtensionFields[name]
	switch definition.Type {
	case "int":
		integer, ok := value.(int)
		if !ok {
			return fmt.Errorf("%s must be int", name)
		}
		if definition.Minimum != nil && integer < *definition.Minimum {
			return fmt.Errorf("%s below minimum", name)
		}
		if definition.Maximum != nil && integer > *definition.Maximum {
			return fmt.Errorf("%s above maximum", name)
		}
	case "string":
		text, ok := value.(string)
		if !ok || strings.TrimSpace(text) == "" || (definition.MaxLength > 0 && utf8.RuneCountInString(text) > definition.MaxLength) {
			return fmt.Errorf("%s is invalid", name)
		}
	case "bool":
		if _, ok := value.(bool); !ok {
			return fmt.Errorf("%s must be bool", name)
		}
	case "string_list":
		values, ok := value.([]string)
		if !ok || len(values) == 0 || len(values) > definition.MaxItems {
			return fmt.Errorf("%s is invalid", name)
		}
		for _, text := range values {
			if strings.TrimSpace(text) == "" || utf8.RuneCountInString(text) > definition.ItemMaxLength {
				return fmt.Errorf("%s item is invalid", name)
			}
		}
	default:
		return fmt.Errorf("unsupported extension type")
	}
	return nil
}

func validateSessionID(value string) error {
	if !strings.HasPrefix(value, "s.") {
		return fmt.Errorf("sessionId prefix invalid")
	}
	separator := strings.LastIndex(value, ".")
	if separator <= 2 || separator == len(value)-1 {
		return fmt.Errorf("sessionId shape invalid")
	}
	if _, err := strconv.ParseInt(value[separator+1:], 10, 64); err != nil {
		return fmt.Errorf("sessionId timestamp invalid")
	}
	encoded := value[2:separator]
	if _, err := base64.RawURLEncoding.DecodeString(encoded); err != nil {
		return fmt.Errorf("sessionId actor invalid")
	}
	return nil
}

func normalizeSummaryQuery(query *EventSummaryQuery, now time.Time) error {
	if query.To.IsZero() {
		query.To = now.Truncate(time.Hour)
	}
	if query.From.IsZero() {
		query.From = query.To.Add(-24 * time.Hour)
	}
	if !query.From.Before(query.To) || query.To.Sub(query.From) > 90*24*time.Hour || query.To.After(now.Add(5*time.Minute)) {
		return ErrInvalidEventQuery
	}
	return nil
}

func validateQueryFilters(logType, eventType, pageName, appVersion, networkClass, errorCode string) error {
	if logType != "" && logType != "event" && logType != "error" {
		return ErrInvalidEventQuery
	}
	if eventType != "" {
		definition, ok := generated.EventCatalog[eventType]
		if !ok || logType != "" && definition.LogType != logType {
			return ErrInvalidEventQuery
		}
	}
	if pageName != "" {
		if _, ok := generated.AppPageNames[pageName]; !ok {
			return ErrInvalidEventQuery
		}
	}
	if networkClass != "" {
		if _, ok := generated.EventNetworkClasses[networkClass]; !ok {
			return ErrInvalidEventQuery
		}
	}
	for _, value := range []string{appVersion, errorCode} {
		if !utf8.ValidString(value) || utf8.RuneCountInString(value) > 128 {
			return ErrInvalidEventQuery
		}
	}
	return nil
}
