package report

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	reportports "quwoquan_service/services/content-service/internal/domain/report/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const (
	reportReceiptTTL  = 24 * time.Hour
	maxReportListSize = 100
)

type ReportService struct {
	data DataPorts
	now  func() time.Time
}

func NewReportService(data DataPorts) *ReportService {
	if data.Aggregate == nil || data.Detail == nil || data.Queue == nil {
		panic("ReportService requires aggregate, detail and queue data ports")
	}
	return &ReportService{
		data: data,
		now:  time.Now,
	}
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
		ID:          reportID,
		ReporterID:  command.ReporterID,
		TargetType:  command.TargetType,
		TargetID:    command.TargetID,
		Reason:      command.Reason,
		Description: command.Description,
		Now:         now,
	})
	if err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	return s.commit(
		ctx,
		aggregate,
		0,
		"CreateReport",
		commandDigest,
		"content.report.created",
		struct {
			ReportID   string                 `json:"reportId"`
			ReporterID string                 `json:"reporterId"`
			TargetType reportmodel.TargetType `json:"targetType"`
			TargetID   string                 `json:"targetId"`
			Reason     reportmodel.Reason     `json:"reason"`
		}{
			ReportID:   reportID,
			ReporterID: strings.TrimSpace(command.ReporterID),
			TargetType: command.TargetType,
			TargetID:   strings.TrimSpace(command.TargetID),
			Reason:     command.Reason,
		},
		now,
	)
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
	expectedVersion := aggregate.Version()
	now := s.now().UTC()
	if err := aggregate.BeginReview(command.ReviewerID, now); err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
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
	expectedVersion := aggregate.Version()
	now := s.now().UTC()
	if err := aggregate.Resolve(
		command.ReviewerID,
		command.Resolution,
		now,
	); err != nil {
		return ReportCommandResult{}, mapDomainError(err)
	}
	return s.commit(
		ctx,
		aggregate,
		expectedVersion,
		"ResolveReport",
		commandDigest,
		"content.report.resolved",
		struct {
			ReportID   string                 `json:"reportId"`
			ReviewerID string                 `json:"reviewerId"`
			Resolution reportmodel.Resolution `json:"resolution"`
		}{
			ReportID:   aggregate.ID(),
			ReviewerID: strings.TrimSpace(command.ReviewerID),
			Resolution: command.Resolution,
		},
		now,
	)
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
	return s.commit(
		ctx,
		aggregate,
		expectedVersion,
		"DismissReport",
		commandDigest,
		"content.report.dismissed",
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
	return contentgenerated.AppErrorFromReportNotFound(
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
