package report

import (
	"context"
	"time"

	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

type CreateReportCommand struct {
	ReporterID  string
	TargetType  reportmodel.TargetType
	TargetID    string
	Reason      reportmodel.Reason
	Description string
}

type BeginReviewReportCommand struct {
	ReportID   string
	ReviewerID string
}

type ResolveReportCommand struct {
	ReportID   string
	ReviewerID string
	Resolution reportmodel.Resolution
}

type DismissReportCommand struct {
	ReportID   string
	ReviewerID string
}

type GetReportQuery struct {
	ReportID string
}

type ListReportsQuery struct {
	Limit int
}

type ListMyReportsQuery struct {
	ReporterID string
	Cursor     string
	Limit      int
}

type MyReportCursor struct {
	CreatedAt time.Time
	ID        string
}

type ReportCommandResult struct {
	ID       string             `json:"id"`
	Version  int64              `json:"version"`
	Status   reportmodel.Status `json:"status"`
	Replayed bool               `json:"replayed,omitempty"`
}

type ReportDetailSlice struct {
	ID          string                 `json:"id"`
	Version     int64                  `json:"version"`
	ReporterID  string                 `json:"reporterId"`
	TargetType  reportmodel.TargetType `json:"targetType"`
	TargetID    string                 `json:"targetId"`
	Reason      reportmodel.Reason     `json:"reason"`
	Description string                 `json:"description,omitempty"`
	Status      reportmodel.Status     `json:"status"`
	ReviewerID  string                 `json:"reviewerId,omitempty"`
	Resolution  reportmodel.Resolution `json:"resolution,omitempty"`
	CreatedAt   time.Time              `json:"createdAt"`
	UpdatedAt   time.Time              `json:"updatedAt"`
	ResolvedAt  *time.Time             `json:"resolvedAt,omitempty"`
}

type ReportQueueItemSlice struct {
	ID         string                 `json:"id"`
	Version    int64                  `json:"version"`
	TargetType reportmodel.TargetType `json:"targetType"`
	TargetID   string                 `json:"targetId"`
	Reason     reportmodel.Reason     `json:"reason"`
	Status     reportmodel.Status     `json:"status"`
	CreatedAt  time.Time              `json:"createdAt"`
	UpdatedAt  time.Time              `json:"updatedAt"`
}

type ReportQueueSlice struct {
	Items []ReportQueueItemSlice `json:"items"`
	Total int                    `json:"total"`
}

type MyReportItemSlice struct {
	ID          string                 `json:"id"`
	TargetType  reportmodel.TargetType `json:"targetType"`
	TargetID    string                 `json:"targetId"`
	Reason      reportmodel.Reason     `json:"reason"`
	Description string                 `json:"description,omitempty"`
	Status      reportmodel.Status     `json:"status"`
	CreatedAt   time.Time              `json:"createdAt"`
	UpdatedAt   time.Time              `json:"updatedAt"`
	ResolvedAt  *time.Time             `json:"resolvedAt,omitempty"`
}

type MyReportPageSlice struct {
	Items      []MyReportItemSlice `json:"items"`
	NextCursor string              `json:"nextCursor,omitempty"`
}

type DetailReader interface {
	FindByID(
		ctx context.Context,
		reportID string,
	) (ReportDetailSlice, bool, error)
}

type QueueReader interface {
	List(ctx context.Context, limit int) (ReportQueueSlice, error)
}

type MyReportReader interface {
	ListByReporter(
		ctx context.Context,
		reporterID string,
		cursor *MyReportCursor,
		limit int,
	) ([]MyReportItemSlice, error)
}
