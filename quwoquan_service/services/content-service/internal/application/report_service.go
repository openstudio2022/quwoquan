package application

import (
	"context"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
	"quwoquan_service/services/content-service/internal/infrastructure/persistence"
)

type ReportService struct {
	store     persistence.ReportRepository
	publisher repository.EventPublisher
}

func NewReportService(store persistence.ReportRepository, publisher repository.EventPublisher) *ReportService {
	return &ReportService{
		store:     store,
		publisher: publisher,
	}
}

func (s *ReportService) CreateReport(ctx context.Context, reporterID string, payload map[string]any) (*reportmodel.Report, error) {
	targetType := strings.TrimSpace(asString(payload["targetType"]))
	targetID := strings.TrimSpace(asString(payload["targetId"]))
	reason := strings.TrimSpace(asString(payload["reason"]))
	description := strings.TrimSpace(asString(payload["description"]))
	if description == "" {
		description = strings.TrimSpace(asString(payload["note"]))
	}
	reporterID = strings.TrimSpace(reporterID)
	if reporterID == "" {
		reporterID = strings.TrimSpace(asString(payload["reporterId"]))
	}

	if reporterID == "" || targetType == "" || targetID == "" || reason == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "举报字段不完整", "reporterId/targetType/targetId/reason are required")
	}

	now := time.Now().UTC()
	report := &reportmodel.Report{
		ID:          fmt.Sprintf("report_%d", now.UnixNano()),
		ReporterID:  reporterID,
		TargetType:  targetType,
		TargetID:    targetID,
		Reason:      reason,
		Description: description,
		Status:      "pending",
		CreatedAt:   now,
	}
	if err := s.store.Create(ctx, report); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "create_report_failed"),
			"提交举报失败",
			err.Error(),
		)
	}

	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "ReportCreated",
			AggregateType: "Report",
			AggregateID:   report.ID,
			Payload: map[string]any{
				"id":         report.ID,
				"reporterId": report.ReporterID,
				"targetType": report.TargetType,
				"targetId":   report.TargetID,
				"reason":     report.Reason,
			},
			OccurredAt: now.Format(time.RFC3339),
		})
	}
	return report, nil
}

func (s *ReportService) GetReport(ctx context.Context, id string) (*reportmodel.Report, error) {
	report, ok, err := s.store.FindByID(ctx, strings.TrimSpace(id))
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "query_report_failed"),
			"查询举报失败",
			err.Error(),
		)
	}
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "report_not_found"),
			"举报不存在",
			"report not found",
		)
	}
	return report, nil
}

func (s *ReportService) ListReports(ctx context.Context, limit int) ([]*reportmodel.Report, error) {
	items, err := s.store.List(ctx, limit)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "list_reports_failed"),
			"查询举报列表失败",
			err.Error(),
		)
	}
	return items, nil
}

func (s *ReportService) ResolveReport(ctx context.Context, reportID, reviewerID string, payload map[string]any) (*reportmodel.Report, error) {
	report, ok, err := s.store.FindByID(ctx, strings.TrimSpace(reportID))
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "query_report_failed"),
			"查询举报失败",
			err.Error(),
		)
	}
	if !ok {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "report_not_found"),
			"举报不存在",
			"report not found",
		)
	}

	nextStatus := strings.TrimSpace(asString(payload["status"]))
	resolution := strings.TrimSpace(asString(payload["resolution"]))
	if nextStatus == "" && resolution == "" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "缺少处理动作", "status or resolution is required")
	}

	switch report.Status {
	case "pending":
		if nextStatus == "reviewing" && resolution == "" {
			report.Status = "reviewing"
		} else if resolution != "" {
			report.Status = resolutionToStatus(resolution)
			report.Resolution = resolution
		} else {
			return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "非法状态流转", "pending can only move to reviewing or resolved/dismissed")
		}
	case "reviewing":
		if resolution == "" {
			return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "reviewing 需要 resolution", "resolution is required when report is reviewing")
		}
		report.Status = resolutionToStatus(resolution)
		report.Resolution = resolution
	default:
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "invalid_report_state"),
			"举报状态不可再处理",
			"report already closed",
		)
	}

	reviewerID = strings.TrimSpace(reviewerID)
	if reviewerID == "" {
		reviewerID = strings.TrimSpace(asString(payload["reviewerId"]))
	}
	if reviewerID != "" {
		report.ReviewerID = reviewerID
	}
	if report.Status == "resolved" || report.Status == "dismissed" {
		now := time.Now().UTC()
		report.ResolvedAt = &now
	}
	if err := s.store.Update(ctx, report); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "update_report_failed"),
			"处理举报失败",
			err.Error(),
		)
	}

	if report.Resolution != "" && s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{
			Type:          "ReportResolved",
			AggregateType: "Report",
			AggregateID:   report.ID,
			Payload: map[string]any{
				"id":         report.ID,
				"targetType": report.TargetType,
				"targetId":   report.TargetID,
				"resolution": report.Resolution,
				"reviewerId": report.ReviewerID,
			},
			OccurredAt: time.Now().UTC().Format(time.RFC3339),
		})
	}
	return report, nil
}

func resolutionToStatus(resolution string) string {
	switch resolution {
	case "dismissed":
		return "dismissed"
	default:
		return "resolved"
	}
}
