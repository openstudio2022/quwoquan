package application

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
)

var (
	ErrInvalidEventBatch = errors.New("invalid event batch")
	ErrBatchInProgress   = errors.New("event batch is still in progress")
	ErrInvalidEventQuery = errors.New("invalid event query")
)

// EventRecordInput 是 /ops/events 唯一 wire shape。它直接由 event_catalog.yaml
// 生成，保证严格 JSON 解码、验证和 SLS 投影不会遗漏已登记的扩展字段。
type EventRecordInput = generated.EventRecordInput

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
	LogType, EventType, PageName, AppVersion, NetworkClass, Result, ErrorCode string
	From, To                                                                  time.Time
}

type EventSummary struct {
	TotalCount        int64                     `json:"totalCount"`
	SessionCount      int64                     `json:"sessionCount"`
	DimensionCounters map[string]map[string]int `json:"dimensions"`
	SourceKind        string                    `json:"sourceKind"`
	Freshness         string                    `json:"freshness"`
	GeneratedThrough  string                    `json:"generatedThrough"`
	LagSeconds        int64                     `json:"lagSeconds"`
	ActualFrom        string                    `json:"actualFrom"`
	ActualTo          string                    `json:"actualTo"`
}

type EventDrilldownQuery struct {
	LogType, EventType, PageName, AppVersion, NetworkClass, Result, ErrorCode, SessionID string
	From, To                                                                             time.Time
	Limit                                                                                int
	RevealSession                                                                        bool
}

type EventDrilldownItem struct {
	RowKey                 string   `json:"rowKey"`
	LogType                string   `json:"logType"`
	EventType              string   `json:"eventType"`
	SessionID              string   `json:"sessionId"`
	PageName               string   `json:"pageName"`
	OccurredAt             string   `json:"occurredAt"`
	DeviceManufacturer     string   `json:"deviceManufacturer"`
	DeviceModel            string   `json:"deviceModel"`
	AppVersion             string   `json:"appVersion"`
	NetworkClass           string   `json:"networkClass"`
	DevicePlatform         string   `json:"devicePlatform"`
	DurationMS             *int     `json:"durationMs,omitempty"`
	Result                 *string  `json:"result,omitempty"`
	CallType               *string  `json:"callType,omitempty"`
	ParticipantCount       *int     `json:"participantCount,omitempty"`
	ConnectTimeMS          *int     `json:"connectTimeMs,omitempty"`
	MediaConnected         *bool    `json:"mediaConnected,omitempty"`
	ReconnectCount         *int     `json:"reconnectCount,omitempty"`
	DisconnectReason       *string  `json:"disconnectReason,omitempty"`
	NetworkQuality         *string  `json:"networkQuality,omitempty"`
	FailReasonCode         *string  `json:"failReasonCode,omitempty"`
	ErrorCode              *string  `json:"errorCode,omitempty"`
	OperationID            *string  `json:"operationId,omitempty"`
	RequestID              *string  `json:"requestId,omitempty"`
	TraceID                *string  `json:"traceId,omitempty"`
	RecoveryAction         *string  `json:"recoveryAction,omitempty"`
	SurfaceID              *string  `json:"surfaceId,omitempty"`
	DetectionSource        *string  `json:"detectionSource,omitempty"`
	TerminalState          *string  `json:"terminalState,omitempty"`
	HTTPStatus             *int     `json:"httpStatus,omitempty"`
	CallStack              []string `json:"callStack,omitempty"`
	TClickToFirstFrameMS   *int     `json:"tClickToFirstFrameMs,omitempty"`
	TFirstFrameToShellMS   *int     `json:"tFirstFrameToShellMs,omitempty"`
	TShellToContentMS      *int     `json:"tShellToContentMs,omitempty"`
	TClickToContentMS      *int     `json:"tClickToContentMs,omitempty"`
	HasError               *bool    `json:"hasError,omitempty"`
	Journey                *string  `json:"journey,omitempty"`
	Action                 *string  `json:"action,omitempty"`
	ReadyMS                *int     `json:"readyMs,omitempty"`
	TTFFMS                 *int     `json:"ttffMs,omitempty"`
	RebufferCount          *int     `json:"rebufferCount,omitempty"`
	RebufferMS             *int     `json:"rebufferMs,omitempty"`
	EffectivePlaybackMS    *int     `json:"effectivePlaybackMs,omitempty"`
	SeekCount              *int     `json:"seekCount,omitempty"`
	SeekFailureCount       *int     `json:"seekFailureCount,omitempty"`
	SeekCommandMaxMS       *int     `json:"seekCommandMaxMs,omitempty"`
	SeekSettleMaxMS        *int     `json:"seekSettleMaxMs,omitempty"`
	DroppedFrames          *int     `json:"droppedFrames,omitempty"`
	ProcessedVideoFrames   *int     `json:"processedVideoFrames,omitempty"`
	AudioUnderrunCount     *int     `json:"audioUnderrunCount,omitempty"`
	RendererMode           *string  `json:"rendererMode,omitempty"`
	DecoderQueueMode       *string  `json:"decoderQueueMode,omitempty"`
	DecoderFallbackEnabled *bool    `json:"decoderFallbackEnabled,omitempty"`
	SeekEvidenceSource     *string  `json:"seekEvidenceSource,omitempty"`
	DeclaredDurationMS     *int     `json:"declaredDurationMs,omitempty"`
	ObservedDurationMS     *int     `json:"observedDurationMs,omitempty"`
	DurationMismatch       *bool    `json:"durationMismatch,omitempty"`
	PlaybackMode           *string  `json:"playbackMode,omitempty"`
	IngestedAt             string   `json:"ingestedAt"`
}

type EventDrilldown struct {
	TotalCount       int64                `json:"totalCount"`
	Items            []EventDrilldownItem `json:"items"`
	SourceKind       string               `json:"sourceKind"`
	Freshness        string               `json:"freshness"`
	GeneratedThrough string               `json:"generatedThrough"`
	LagSeconds       int64                `json:"lagSeconds"`
	ActualFrom       string               `json:"actualFrom"`
	ActualTo         string               `json:"actualTo"`
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

type EventLogStore interface {
	PutEventBatch(context.Context, string, []EventRecord) error
	HasEventBatch(context.Context, string, int) (bool, error)
	GetEventSummary(context.Context, EventSummaryQuery) (EventSummary, error)
	GetEventDrilldown(context.Context, EventDrilldownQuery) (EventDrilldown, error)
	PutStartupDiagnostics(context.Context, string, []StartupDiagnosticRecord) error
	HasStartupDiagnosticBatch(context.Context, string, int) (bool, error)
	// GetPageExperienceStats 按 pageName 聚合页面体验事实（打开次数、逐页 TTI
	// 均值、停留均值、错误次数），供页面矩阵热力图消费；无数据页面不合成。
	GetPageExperienceStats(context.Context, PageExperienceQuery) ([]PageExperienceStat, error)
}

// IncompleteEventBatchRepairer is an optional Port capability for stores whose
// writes use deterministic identities. It lets a retry repair a partially
// persisted pending batch without exposing or branching on the Provider.
type IncompleteEventBatchRepairer interface {
	RepairEventBatch(context.Context, string, []EventRecord) error
	RepairStartupDiagnosticBatch(
		context.Context,
		string,
		[]StartupDiagnosticRecord,
	) error
}

type PageExperienceQuery struct {
	From, To time.Time
}

type PageExperienceStat struct {
	PageName      string  `json:"pageName"`
	Opens         int64   `json:"opens"`
	AvgReadyMs    float64 `json:"avgReadyMs"`
	ReadySamples  int64   `json:"readySamples"`
	AvgStayMs     float64 `json:"avgStayMs"`
	StaySamples   int64   `json:"staySamples"`
	RuntimeErrors int64   `json:"runtimeErrors"`
}

type BatchLedgerState string

type EventBatchLedger interface {
	Begin(context.Context, string, int) (BatchLedgerState, error)
	MarkAccepted(context.Context, string, int) error
}

const (
	BatchLedgerNew      BatchLedgerState = "new"
	BatchLedgerPending  BatchLedgerState = "pending"
	BatchLedgerAccepted BatchLedgerState = "accepted"
)

type TelemetryService struct {
	events      EventLogStore
	ledger      EventBatchLedger
	rtcMediaQoe RtcMediaQoeSummaryReader
	now         func() time.Time
}

func NewTelemetryService(
	events EventLogStore,
	ledger EventBatchLedger,
) *TelemetryService {
	return NewTelemetryServiceWithStores(events, ledger)
}

func NewTelemetryServiceWithStores(
	events EventLogStore,
	ledger EventBatchLedger,
) *TelemetryService {
	return &TelemetryService{events: events, ledger: ledger, now: time.Now}
}

func NewTelemetryServiceWithStoresAndRtcMediaQoeReader(
	events EventLogStore,
	ledger EventBatchLedger,
	rtcMediaQoe RtcMediaQoeSummaryReader,
) *TelemetryService {
	service := NewTelemetryServiceWithStores(events, ledger)
	service.rtcMediaQoe = rtcMediaQoe
	return service
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
			repairer, repairable := s.events.(IncompleteEventBatchRepairer)
			if !repairable {
				return EventBatchAck{}, ErrBatchInProgress
			}
			if err := repairer.RepairEventBatch(ctx, batchKey, records); err != nil {
				return EventBatchAck{}, err
			}
			confirmed, confirmErr = s.events.HasEventBatch(
				ctx,
				batchKey,
				len(records),
			)
			if confirmErr != nil {
				return EventBatchAck{}, confirmErr
			}
			if !confirmed {
				return EventBatchAck{}, ErrBatchInProgress
			}
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
	// proof 只用于匿名入口的防滥用与限流，不是批次身份。使用本批完整
	// canonical body 计算 digest，避免同一启动 proof 的第二批事件被误判 duplicate。
	canonical, err := json.Marshal(records)
	if err != nil {
		return EventBatchAck{}, fmt.Errorf("%w: startup batch canonicalization failed", ErrInvalidEventBatch)
	}
	digest := sha256.Sum256(append([]byte("startup:"), canonical...))
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
			repairer, repairable := s.events.(IncompleteEventBatchRepairer)
			if !repairable {
				return EventBatchAck{}, ErrBatchInProgress
			}
			if err := repairer.RepairStartupDiagnosticBatch(
				ctx,
				batchKey,
				records,
			); err != nil {
				return EventBatchAck{}, err
			}
			confirmed, confirmErr = s.events.HasStartupDiagnosticBatch(
				ctx,
				batchKey,
				len(records),
			)
			if confirmErr != nil {
				return EventBatchAck{}, confirmErr
			}
			if !confirmed {
				return EventBatchAck{}, ErrBatchInProgress
			}
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

// GetPageExperience 返回窗口内按 pageName 聚合的页面体验事实（热力图数据源）。
func (s *TelemetryService) GetPageExperience(
	ctx context.Context,
	query PageExperienceQuery,
) ([]PageExperienceStat, error) {
	now := s.now().UTC()
	if query.To.IsZero() {
		query.To = now
	}
	if query.From.IsZero() {
		query.From = query.To.Add(-24 * time.Hour)
	}
	if !query.From.Before(query.To) ||
		query.To.Sub(query.From) > 72*time.Hour ||
		query.To.After(now.Add(5*time.Minute)) {
		return nil, ErrInvalidEventQuery
	}
	return s.events.GetPageExperienceStats(ctx, query)
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
	if _, ok := generated.EventContextExtensions["devicePlatform"]; !ok {
		return fmt.Errorf("devicePlatform is not registered as a context extension")
	}
	devicePlatformDefinition := generated.EventExtensionFields["devicePlatform"]
	if _, ok := devicePlatformDefinition.AllowedValues[input.DevicePlatform]; !ok {
		return fmt.Errorf("unknown devicePlatform")
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
	extensions := input.ExtensionValues()
	extensions["devicePlatform"] = input.DevicePlatform
	for required := range definition.RequiredExtensions {
		if _, ok := extensions[required]; !ok {
			return fmt.Errorf("missing extension %s", required)
		}
	}
	for name, value := range extensions {
		if _, ok := definition.RequiredExtensions[name]; !ok {
			if _, ok := definition.OptionalExtensions[name]; !ok {
				if _, ok := generated.EventContextExtensions[name]; !ok {
					return fmt.Errorf("unknown extension %s", name)
				}
			}
		}
		if err := validateExtension(name, value); err != nil {
			return err
		}
	}
	return nil
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
		if len(definition.AllowedValues) > 0 {
			if _, allowed := definition.AllowedValues[text]; !allowed {
				return fmt.Errorf("%s is not an allowed value", name)
			}
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
