package report

import (
	"context"
	"time"

	reportmodel "quwoquan_service/services/content-service/internal/trust_safety/report/domain/model"
)

type CreateReportCommand struct {
	ReporterID        string
	ReporterAccountID string
	TargetType        reportmodel.TargetType
	TargetID          string
	Reason            reportmodel.Reason
	Description       string
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

type GrantGatheringSafetyTerminationCommand struct {
	ReportID              string
	ExpectedReportVersion int64
	ActorPersonaID        string
	ExpiresAt             time.Time
	IdempotencyKey        string
}

type RevokeGatheringSafetyTerminationCommand struct {
	ReportID       string
	DecisionRef    string
	IdempotencyKey string
}

type AuthorizeGatheringSafetyTerminationQuery struct {
	ActorPersonaID string
	GatheringID    string
	Action         string
	EvidenceRef    string
	DecisionRef    string
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
	Replayed bool               `json:"replayed"`
}

type GatheringSafetyTerminationGrantResult struct {
	ActorPersonaID  string     `json:"actorPersonaId"`
	GatheringID     string     `json:"gatheringId"`
	Action          string     `json:"action"`
	EvidenceRef     string     `json:"evidenceRef"`
	DecisionRef     string     `json:"decisionRef"`
	DecisionVersion int64      `json:"decisionVersion"`
	DecisionDigest  string     `json:"decisionDigest"`
	ExpiresAt       time.Time  `json:"expiresAt"`
	RevokedAt       *time.Time `json:"revokedAt,omitempty"`
	Replayed        bool       `json:"replayed"`
}

type GatheringSafetyTerminationAuthoritySlice struct {
	Allowed         bool       `json:"allowed"`
	ActorPersonaID  string     `json:"actorPersonaId,omitempty"`
	GatheringID     string     `json:"gatheringId,omitempty"`
	Action          string     `json:"action,omitempty"`
	EvidenceRef     string     `json:"evidenceRef,omitempty"`
	DecisionRef     string     `json:"decisionRef,omitempty"`
	DecisionVersion int64      `json:"decisionVersion,omitempty"`
	DecisionDigest  string     `json:"decisionDigest,omitempty"`
	ExpiresAt       *time.Time `json:"expiresAt,omitempty"`
	RevokedAt       *time.Time `json:"revokedAt,omitempty"`
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
