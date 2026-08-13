package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	"quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventdomain "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/domain"
)

var (
	ErrInvalidEventBatch = errors.New("invalid event batch")
	ErrBatchInProgress   = errors.New("event batch is still in progress")
	ErrInvalidEventQuery = errors.New("invalid event query")
)

// EventRecordInput 是 /ops/events 唯一 wire shape。它直接由 event_catalog.yaml
// 生成，保证严格 JSON 解码、验证和 Elasticsearch 投影不会遗漏已登记的扩展字段。
type EventRecordInput = eventdomain.Input
type EventRecord = eventdomain.Fact

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
	EventID, AttemptID, Phase, Outcome, OccurredAt, Platform, RuntimeEnv string
	AppVersion, NetworkClass, RecoverySurface                            string
	RecoveryLifecycle, RecoveryMount, RecoveryPhase, RecoveryAction      string
	FailureCode, FailureSource, DeadlineOrigin                           string
	Sequence, PhaseDurationMS, ElapsedMS                                 int
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
	// GetEventValueStats 读取窗口内某事件数值字段的 P95 与求和统计
	// （raw 权威回读，与 RTC QoE 同一原始样本口径），承载黄金指标
	// percentile / sum_ratio 形态的实时计算；无样本显式零计数，不合成。
	GetEventValueStats(context.Context, EventValueStatsQuery) (EventValueStats, error)
}

// EventValueStatsQuery 的 ValueField 服务 percentile 形态；
// Numerator/DenominatorField 服务 sum_ratio 形态，两组互斥使用。
type EventValueStatsQuery struct {
	EventType        string
	Result           string
	ValueField       string
	NumeratorField   string
	DenominatorField string
	From, To         time.Time
}

type EventValueStats struct {
	SampleCount    int64   `json:"sampleCount"`
	P95            float64 `json:"p95"`
	NumeratorSum   float64 `json:"numeratorSum"`
	DenominatorSum float64 `json:"denominatorSum"`
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
		record, err := eventdomain.NewFact(input, batchKey, index, now)
		if err != nil {
			return EventBatchAck{}, fmt.Errorf("%w: event[%d]: %v", ErrInvalidEventBatch, index, err)
		}
		records[index] = record
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

// GetEventValueStats 校验事件与字段后读取原始样本统计。字段必须是该
// 事件在 event_catalog 声明的数值扩展，禁止自由字段透传到存储查询。
func (s *TelemetryService) GetEventValueStats(
	ctx context.Context,
	query EventValueStatsQuery,
) (EventValueStats, error) {
	summaryWindow := EventSummaryQuery{From: query.From, To: query.To}
	if err := normalizeSummaryQuery(&summaryWindow, s.now().UTC()); err != nil {
		return EventValueStats{}, err
	}
	query.From, query.To = summaryWindow.From, summaryWindow.To
	definition, ok := generated.EventCatalog[query.EventType]
	if !ok {
		return EventValueStats{}, ErrInvalidEventQuery
	}
	fields := make([]string, 0, 3)
	if query.ValueField != "" {
		fields = append(fields, query.ValueField)
	}
	if query.NumeratorField != "" {
		fields = append(fields, query.NumeratorField)
	}
	if query.DenominatorField != "" {
		fields = append(fields, query.DenominatorField)
	}
	if len(fields) == 0 {
		return EventValueStats{}, ErrInvalidEventQuery
	}
	for _, field := range fields {
		_, required := definition.RequiredExtensions[field]
		_, optional := definition.OptionalExtensions[field]
		if !required && !optional {
			return EventValueStats{}, ErrInvalidEventQuery
		}
	}
	return s.events.GetEventValueStats(ctx, query)
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
		if err := eventdomain.ValidateSessionID(query.SessionID); err != nil {
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
