package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	runtimeobservability "quwoquan_service/runtime/observability"
)

var ErrInvalidRuntimeLogBatch = fmt.Errorf("invalid runtime log batch")

// RuntimeLogRecord 是写入 SLS 前已由 runtime/observability 严格校验并扁平化的
// 诊断事实。业务层不持有自由 JSON，避免日志入口演变成旁路协议。
type RuntimeLogRecord struct {
	Fields     map[string]string
	BatchKey   string
	BatchIndex int
	IngestedAt time.Time
}

type RuntimeLogStore interface {
	PutRuntimeLogBatch(context.Context, string, []RuntimeLogRecord) error
	HasRuntimeLogBatch(context.Context, string, int) (bool, error)
	GetRuntimeLogSummary(context.Context, RuntimeLogSummaryQuery) (RuntimeLogSummary, error)
	GetRuntimeLogDrilldown(context.Context, RuntimeLogDrilldownQuery) (RuntimeLogDrilldown, error)
}

type RuntimeLogSummaryQuery struct {
	Signal, Severity, ErrorCode, Fingerprint, SourceType, Service, AppVersion string
	From, To                                                                  time.Time
}

type RuntimeLogSummary struct {
	TotalCount        int64                     `json:"totalCount"`
	DimensionCounters map[string]map[string]int `json:"dimensions"`
	SourceKind        string                    `json:"sourceKind"`
	Freshness         string                    `json:"freshness"`
	GeneratedThrough  string                    `json:"generatedThrough"`
	LagSeconds        int64                     `json:"lagSeconds"`
	ActualFrom        string                    `json:"actualFrom"`
	ActualTo          string                    `json:"actualTo"`
}

type RuntimeLogDrilldownQuery struct {
	Signal, Severity, ErrorCode, Fingerprint, SourceType, Service, AppVersion string
	// ActorHash 支持"按用户查日志"（敏感权限已在 transport 层校验）；
	// MessageContains 支持日志文本检索（SLS 全文索引短语匹配）。
	ActorHash, MessageContains string
	From, To                   time.Time
	Limit                      int
	RevealCorrelation          bool
}

type RuntimeLogDrilldownItem struct {
	RowKey      string            `json:"rowKey"`
	RecordID    string            `json:"recordId,omitempty"`
	OccurredAt  string            `json:"occurredAt"`
	ObservedAt  string            `json:"observedAt"`
	LogKind     string            `json:"logKind"`
	Severity    string            `json:"severity"`
	Signal      string            `json:"signal"`
	Message     string            `json:"message"`
	ErrorCode   string            `json:"errorCode,omitempty"`
	Fingerprint string            `json:"fingerprint,omitempty"`
	Resource    map[string]string `json:"resource"`
	Correlation map[string]string `json:"correlation,omitempty"`
	Attributes  map[string]string `json:"attributes,omitempty"`
	IngestedAt  string            `json:"ingestedAt"`
}

type RuntimeLogDrilldown struct {
	TotalCount       int64                     `json:"totalCount"`
	Items            []RuntimeLogDrilldownItem `json:"items"`
	SourceKind       string                    `json:"sourceKind"`
	Freshness        string                    `json:"freshness"`
	GeneratedThrough string                    `json:"generatedThrough"`
	LagSeconds       int64                     `json:"lagSeconds"`
	ActualFrom       string                    `json:"actualFrom"`
	ActualTo         string                    `json:"actualTo"`
}

type RuntimeLogService struct {
	store  RuntimeLogStore
	ledger EventBatchLedger
	now    func() time.Time
}

func NewRuntimeLogService(store RuntimeLogStore, ledger EventBatchLedger) *RuntimeLogService {
	if store == nil || ledger == nil {
		panic("runtime log service requires store and ledger")
	}
	return &RuntimeLogService{store: store, ledger: ledger, now: time.Now}
}

// ReportRuntimeLogBatch 是所有已登记 producer 的统一入口。signal 的第一个段必须
// 与 resource.sourceType 相同，阻止客户端把 app 日志伪造成 service/ops/data/portal
// 记录；跨语言 exporter 仍共用同一个 canonical runtime log contract。
func (s *RuntimeLogService) ReportRuntimeLogBatch(
	ctx context.Context,
	batchKey string,
	inputs []map[string]any,
) (EventBatchAck, error) {
	if len(inputs) == 0 ||
		len(inputs) > runtimeobservability.CatalogMaxBatchItems ||
		len(batchKey) != 64 {
		return EventBatchAck{}, ErrInvalidRuntimeLogBatch
	}
	now := s.now().UTC()
	records := make([]RuntimeLogRecord, len(inputs))
	for index, input := range inputs {
		fields, err := runtimeobservability.CanonicalRuntimeLogFields(input)
		if err != nil {
			return EventBatchAck{}, fmt.Errorf("%w: record[%d]: %v", ErrInvalidRuntimeLogBatch, index, err)
		}
		signalPrefix, _, hasSeparator := strings.Cut(fields["signal"], ".")
		if !hasSeparator ||
			fields["resourceSourceType"] != signalPrefix ||
			strings.TrimSpace(fields["resourceService"]) == "" ||
			(fields["resourceSourceType"] == "app" && strings.TrimSpace(fields["resourceAppVersion"]) == "") {
			return EventBatchAck{}, fmt.Errorf("%w: record[%d] has an invalid producer resource", ErrInvalidRuntimeLogBatch, index)
		}
		occurredAt, err := time.Parse(time.RFC3339Nano, fields["occurredAt"])
		if err != nil ||
			occurredAt.Before(now.Add(-72*time.Hour)) ||
			occurredAt.After(now.Add(5*time.Minute)) {
			return EventBatchAck{}, fmt.Errorf("%w: record[%d] occurredAt outside accepted window", ErrInvalidRuntimeLogBatch, index)
		}
		records[index] = RuntimeLogRecord{
			Fields:     fields,
			BatchKey:   batchKey,
			BatchIndex: index,
			IngestedAt: now,
		}
	}

	state, err := s.ledger.Begin(ctx, "runtime:"+batchKey, len(records))
	if err != nil {
		return EventBatchAck{}, err
	}
	if state == BatchLedgerAccepted {
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if state == BatchLedgerPending {
		confirmed, confirmErr := s.store.HasRuntimeLogBatch(ctx, batchKey, len(records))
		if confirmErr != nil {
			return EventBatchAck{}, confirmErr
		}
		if !confirmed {
			return EventBatchAck{}, ErrBatchInProgress
		}
		if err := s.ledger.MarkAccepted(ctx, "runtime:"+batchKey, len(records)); err != nil {
			return EventBatchAck{}, err
		}
		return EventBatchAck{AcceptedCount: len(records), DuplicateBatch: true}, nil
	}
	if err := s.store.PutRuntimeLogBatch(ctx, batchKey, records); err != nil {
		confirmed, confirmErr := s.store.HasRuntimeLogBatch(ctx, batchKey, len(records))
		if confirmErr != nil || !confirmed {
			return EventBatchAck{}, err
		}
	}
	if err := s.ledger.MarkAccepted(ctx, "runtime:"+batchKey, len(records)); err != nil {
		return EventBatchAck{}, err
	}
	return EventBatchAck{AcceptedCount: len(records)}, nil
}

func (s *RuntimeLogService) GetRuntimeLogSummary(ctx context.Context, query RuntimeLogSummaryQuery) (RuntimeLogSummary, error) {
	now := s.now().UTC()
	if query.From.IsZero() {
		query.From = now.Add(-24 * time.Hour)
	}
	if query.To.IsZero() {
		query.To = now
	}
	if !query.From.Before(query.To) ||
		query.To.Sub(query.From) > 90*24*time.Hour ||
		query.To.After(now.Add(5*time.Minute)) {
		return RuntimeLogSummary{}, ErrInvalidEventQuery
	}
	return s.store.GetRuntimeLogSummary(ctx, query)
}

func (s *RuntimeLogService) GetRuntimeLogDrilldown(ctx context.Context, query RuntimeLogDrilldownQuery) (RuntimeLogDrilldown, error) {
	now := s.now().UTC()
	if query.From.IsZero() ||
		query.To.IsZero() ||
		!query.From.Before(query.To) ||
		query.To.Sub(query.From) > 72*time.Hour ||
		query.From.Before(now.Add(-72*time.Hour)) ||
		query.To.After(now.Add(5*time.Minute)) {
		return RuntimeLogDrilldown{}, ErrInvalidEventQuery
	}
	if query.Limit <= 0 {
		query.Limit = 50
	}
	if query.Limit > 100 {
		return RuntimeLogDrilldown{}, ErrInvalidEventQuery
	}
	return s.store.GetRuntimeLogDrilldown(ctx, query)
}
