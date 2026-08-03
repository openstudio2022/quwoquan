package report

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	reporterrors "quwoquan_service/services/content-service/generated/trust_safety/report"
	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const (
	reportReceiptTTL  = 24 * time.Hour
	maxReportListSize = 100
)

type ReportService struct {
	data     DataPorts
	now      func() time.Time
	observer LifecycleObserver
}

func NewReportService(
	data DataPorts,
	options ...ReportServiceOption,
) *ReportService {
	if data.Aggregate == nil ||
		data.Detail == nil ||
		data.Queue == nil ||
		data.MyReports == nil {
		panic("ReportService requires aggregate, detail, queue and reporter data ports")
	}
	service := &ReportService{
		data: data,
		now:  time.Now,
	}
	for _, option := range options {
		option(service)
	}
	return service
}

func (s *ReportService) CreateReport(
	ctx context.Context,
	command CreateReportCommand,
) (ReportCommandResult, error) {
	commandDigest := reportCommandDigest("CreateReport", command)
	if replayed, found, err := s.replay(ctx, "CreateReport", commandDigest); err != nil || found {
		return replayed, err
	}
	now := s.now().UTC()
	reportID, err := newReportIdentifier("rpt")
	if err != nil {
		return ReportCommandResult{}, unavailable(err)
	}
	aggregate, err := reportmodel.Create(reportmodel.CreateParams{
		ID:                reportID,
		ReporterID:        command.ReporterID,
		ReporterAccountID: command.ReporterAccountID,
		TargetType:        command.TargetType,
		TargetID:          command.TargetID,
		Reason:            command.Reason,
		Description:       command.Description,
		Now:               now,
	})
	if err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	result, err := s.commit(
		ctx,
		aggregate,
		0,
		"CreateReport",
		commandDigest,
		"content.report.created",
		struct {
			ReportID          string                 `json:"reportId"`
			ReporterID        string                 `json:"reporterId"`
			ReporterAccountID string                 `json:"reporterAccountId"`
			TargetType        reportmodel.TargetType `json:"targetType"`
			TargetID          string                 `json:"targetId"`
			Reason            reportmodel.Reason     `json:"reason"`
		}{
			ReportID:          reportID,
			ReporterID:        strings.TrimSpace(command.ReporterID),
			ReporterAccountID: strings.TrimSpace(command.ReporterAccountID),
			TargetType:        command.TargetType,
			TargetID:          strings.TrimSpace(command.TargetID),
			Reason:            command.Reason,
		},
		now,
	)
	if err == nil && s.observer != nil {
		s.observer.ReportCreated(ctx)
	}
	return result, err
}

func (s *ReportService) BeginReview(
	ctx context.Context,
	command BeginReviewReportCommand,
) (ReportCommandResult, error) {
	commandDigest := reportCommandDigest("BeginReviewReport", command)
	if replayed, found, err := s.replay(
		ctx,
		"BeginReviewReport",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	aggregate, found, err := s.load(ctx, command.ReportID)
	if err != nil {
		return ReportCommandResult{}, err
	}
	if !found {
		return ReportCommandResult{}, reportNotFound(command.ReportID)
	}
	// 目标状态已满足（同一 reviewer 已开始审核）：持久化 no-op receipt，
	// 不递增版本、不制造伪 review_started 事实。
	if snapshot := aggregate.Snapshot(); snapshot.Status == reportmodel.StatusReviewing &&
		snapshot.ReviewerID == strings.TrimSpace(command.ReviewerID) {
		return s.recordNoopReceipt(ctx, aggregate, "BeginReviewReport", commandDigest)
	}
	expectedVersion := aggregate.Version()
	now := s.now().UTC()
	if err := aggregate.BeginReview(command.ReviewerID, now); err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	// BeginReview 不是关闭事件：ReportClosed 观测只在 Resolve/Dismiss 发射
	// （那里 snapshot 在 commit 前捕获，本方法无 closed 语义）。
	return s.commit(
		ctx,
		aggregate,
		expectedVersion,
		"BeginReviewReport",
		commandDigest,
		"content.report.review_started",
		struct {
			ReportID   string `json:"reportId"`
			ReviewerID string `json:"reviewerId"`
		}{
			ReportID:   aggregate.ID(),
			ReviewerID: strings.TrimSpace(command.ReviewerID),
		},
		now,
	)
}

func (s *ReportService) Resolve(
	ctx context.Context,
	command ResolveReportCommand,
) (ReportCommandResult, error) {
	commandDigest := reportCommandDigest("ResolveReport", command)
	if replayed, found, err := s.replay(
		ctx,
		"ResolveReport",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	aggregate, found, err := s.load(ctx, command.ReportID)
	if err != nil {
		return ReportCommandResult{}, err
	}
	if !found {
		return ReportCommandResult{}, reportNotFound(command.ReportID)
	}
	// 目标状态已满足（同一 reviewer 已用同一 resolution 结案）：持久化
	// no-op receipt，不递增版本、不重复投递 resolved 事实。
	if snapshot := aggregate.Snapshot(); snapshot.Status == reportmodel.StatusResolved &&
		snapshot.ReviewerID == strings.TrimSpace(command.ReviewerID) &&
		snapshot.Resolution == command.Resolution {
		return s.recordNoopReceipt(ctx, aggregate, "ResolveReport", commandDigest)
	}
	expectedVersion := aggregate.Version()
	now := s.now().UTC()
	if err := aggregate.Resolve(
		command.ReviewerID,
		command.Resolution,
		now,
	); err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	snapshot := aggregate.Snapshot()
	result, err := s.commit(
		ctx,
		aggregate,
		expectedVersion,
		"ResolveReport",
		commandDigest,
		"content.report.resolved",
		struct {
			ReportID          string                 `json:"reportId"`
			ReporterID        string                 `json:"reporterId"`
			ReporterAccountID string                 `json:"reporterAccountId"`
			TargetType        reportmodel.TargetType `json:"targetType"`
			TargetID          string                 `json:"targetId"`
			ReviewerID        string                 `json:"reviewerId"`
			Resolution        reportmodel.Resolution `json:"resolution"`
		}{
			ReportID:          aggregate.ID(),
			ReporterID:        snapshot.ReporterID,
			ReporterAccountID: snapshot.ReporterAccountID,
			TargetType:        snapshot.TargetType,
			TargetID:          snapshot.TargetID,
			ReviewerID:        strings.TrimSpace(command.ReviewerID),
			Resolution:        command.Resolution,
		},
		now,
	)
	if err == nil && s.observer != nil {
		s.observer.ReportClosed(
			ctx,
			string(reportmodel.StatusResolved),
			snapshot.CreatedAt,
			now,
		)
	}
	return result, err
}

func (s *ReportService) Dismiss(
	ctx context.Context,
	command DismissReportCommand,
) (ReportCommandResult, error) {
	commandDigest := reportCommandDigest("DismissReport", command)
	if replayed, found, err := s.replay(
		ctx,
		"DismissReport",
		commandDigest,
	); err != nil || found {
		return replayed, err
	}
	aggregate, found, err := s.load(ctx, command.ReportID)
	if err != nil {
		return ReportCommandResult{}, err
	}
	if !found {
		return ReportCommandResult{}, reportNotFound(command.ReportID)
	}
	expectedVersion := aggregate.Version()
	now := s.now().UTC()
	if err := aggregate.Dismiss(command.ReviewerID, now); err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	snapshot := aggregate.Snapshot()
	result, err := s.commit(
		ctx,
		aggregate,
		expectedVersion,
		"DismissReport",
		commandDigest,
		"content.report.dismissed",
		struct {
			ReportID          string                 `json:"reportId"`
			ReporterID        string                 `json:"reporterId"`
			ReporterAccountID string                 `json:"reporterAccountId"`
			TargetType        reportmodel.TargetType `json:"targetType"`
			TargetID          string                 `json:"targetId"`
			ReviewerID        string                 `json:"reviewerId"`
		}{
			ReportID:          aggregate.ID(),
			ReporterID:        snapshot.ReporterID,
			ReporterAccountID: snapshot.ReporterAccountID,
			TargetType:        snapshot.TargetType,
			TargetID:          snapshot.TargetID,
			ReviewerID:        strings.TrimSpace(command.ReviewerID),
		},
		now,
	)
	if err == nil && s.observer != nil {
		s.observer.ReportClosed(
			ctx,
			string(reportmodel.StatusDismissed),
			snapshot.CreatedAt,
			now,
		)
	}
	return result, err
}

func (s *ReportService) GetReport(
	ctx context.Context,
	query GetReportQuery,
) (ReportDetailSlice, error) {
	slice, found, err := s.data.Detail.FindByID(
		ctx,
		strings.TrimSpace(query.ReportID),
	)
	if err != nil {
		return ReportDetailSlice{}, unavailable(err)
	}
	if !found {
		return ReportDetailSlice{}, reportNotFound(query.ReportID)
	}
	return slice, nil
}

func (s *ReportService) ListReports(
	ctx context.Context,
	query ListReportsQuery,
) (ReportQueueSlice, error) {
	limit := query.Limit
	if limit <= 0 || limit > maxReportListSize {
		limit = 20
	}
	slice, err := s.data.Queue.List(ctx, limit)
	if err != nil {
		return ReportQueueSlice{}, unavailable(err)
	}
	return slice, nil
}

func (s *ReportService) ListMyReports(
	ctx context.Context,
	query ListMyReportsQuery,
) (MyReportPageSlice, error) {
	reporterID := strings.TrimSpace(query.ReporterID)
	if reporterID == "" {
		return MyReportPageSlice{}, contentgenerated.AppErrorFromUnauthorized(
			"ListMyReports requires a verified persona",
		)
	}
	limit := query.Limit
	if limit <= 0 || limit > maxReportListSize {
		limit = 20
	}
	cursor, err := decodeMyReportCursor(query.Cursor)
	if err != nil {
		return MyReportPageSlice{}, contentgenerated.AppErrorFromInvalidArgument(
			"ListMyReports cursor is invalid",
		)
	}
	items, err := s.data.MyReports.ListByReporter(
		ctx,
		reporterID,
		cursor,
		limit+1,
	)
	if err != nil {
		return MyReportPageSlice{}, unavailable(err)
	}
	page := MyReportPageSlice{Items: items}
	if len(items) > limit {
		page.Items = items[:limit]
		last := page.Items[len(page.Items)-1]
		page.NextCursor = encodeMyReportCursor(MyReportCursor{
			CreatedAt: last.CreatedAt,
			ID:        last.ID,
		})
	}
	return page, nil
}

func encodeMyReportCursor(cursor MyReportCursor) string {
	payload := cursor.CreatedAt.UTC().Format(time.RFC3339Nano) + "\n" +
		strings.TrimSpace(cursor.ID)
	return base64.RawURLEncoding.EncodeToString([]byte(payload))
}

func decodeMyReportCursor(raw string) (*MyReportCursor, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}
	payload, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return nil, err
	}
	parts := strings.Split(string(payload), "\n")
	if len(parts) != 2 || strings.TrimSpace(parts[1]) == "" {
		return nil, errors.New("invalid report cursor payload")
	}
	createdAt, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return nil, err
	}
	return &MyReportCursor{
		CreatedAt: createdAt.UTC(),
		ID:        strings.TrimSpace(parts[1]),
	}, nil
}

func (s *ReportService) load(
	ctx context.Context,
	reportID string,
) (*reportmodel.Report, bool, error) {
	aggregate, found, err := s.data.Aggregate.Load(
		ctx,
		strings.TrimSpace(reportID),
	)
	if err != nil {
		return nil, false, unavailable(err)
	}
	return aggregate, found, nil
}

func (s *ReportService) replay(
	ctx context.Context,
	commandName string,
	commandDigest string,
) (ReportCommandResult, bool, error) {
	idempotencyKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if idempotencyKey == "" {
		return ReportCommandResult{},
			false,
			rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"idempotencyKey 必填",
				"report command requires idempotencyKey",
			)
	}
	result, found, err := s.data.Aggregate.FindReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return ReportCommandResult{}, false, unavailable(err)
	}
	if !found {
		return ReportCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return ReportCommandResult{},
			false,
			unavailable(errors.New("report receipt has no aggregate"))
	}
	return ReportCommandResult{
		ID:       result.Aggregate.ID(),
		Version:  result.Aggregate.Version(),
		Status:   result.Aggregate.Status(),
		Replayed: true,
	}, true, nil
}

// recordNoopReceipt 处理"目标状态已满足"的命名迁移：持久化幂等回执供后续重放，
// 不递增聚合版本、不投递伪事实事件。
func (s *ReportService) recordNoopReceipt(
	ctx context.Context,
	aggregate *reportmodel.Report,
	commandName string,
	commandDigest string,
) (ReportCommandResult, error) {
	idempotencyKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if idempotencyKey == "" {
		return ReportCommandResult{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			"report command requires idempotencyKey",
		)
	}
	result, err := s.data.Aggregate.RecordNoopReceipt(ctx, reportports.NoopReceipt{
		Aggregate:        aggregate,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: s.now().UTC().Add(reportReceiptTTL),
	})
	if err != nil {
		return ReportCommandResult{}, unavailable(err)
	}
	return ReportCommandResult{
		ID:       result.Aggregate.ID(),
		Version:  result.Aggregate.Version(),
		Status:   result.Aggregate.Status(),
		Replayed: result.Replayed,
	}, nil
}

func (s *ReportService) commit(
	ctx context.Context,
	aggregate *reportmodel.Report,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload any,
	now time.Time,
) (ReportCommandResult, error) {
	idempotencyKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if idempotencyKey == "" {
		return ReportCommandResult{}, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"idempotencyKey 必填",
			"report command requires idempotencyKey",
		)
	}
	payload, err := json.Marshal(eventPayload)
	if err != nil {
		return ReportCommandResult{}, unavailable(err)
	}
	eventID, err := newReportIdentifier("evt")
	if err != nil {
		return ReportCommandResult{}, unavailable(err)
	}
	result, err := s.data.Aggregate.Commit(ctx, reportports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.Add(reportReceiptTTL),
		Events: []reportports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          payload,
			OccurredAt:       now,
		}},
	})
	if err != nil {
		return ReportCommandResult{}, unavailable(err)
	}
	return ReportCommandResult{
		ID:       result.Aggregate.ID(),
		Version:  result.Aggregate.Version(),
		Status:   result.Aggregate.Status(),
		Replayed: result.Replayed,
	}, nil
}

func reportCommandDigest(commandName string, payload any) string {
	raw, _ := json.Marshal(struct {
		Command string `json:"command"`
		Payload any    `json:"payload"`
	}{
		Command: commandName,
		Payload: payload,
	})
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, reportmodel.ErrInvalidReport),
		errors.Is(err, reportmodel.ErrInvalidTransition):
		return rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"举报状态或参数不合法",
			err.Error(),
		)
	default:
		return err
	}
}

func reportNotFound(reportID string) error {
	return reporterrors.AppErrorFromReportNotFound(
		fmt.Sprintf("report %s not found", strings.TrimSpace(reportID)),
	)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return rterr.NewUnavailable(
		rterr.ModuleContent,
		"举报服务暂时不可用",
		err.Error(),
	)
}

func newReportIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}
