package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidReport     = errors.New("invalid report")
	ErrInvalidTransition = errors.New("invalid report transition")
)

type TargetType string

const (
	TargetPost    TargetType = "post"
	TargetComment TargetType = "comment"
	TargetUser    TargetType = "user"
	TargetCircle  TargetType = "circle"
	TargetMessage TargetType = "message"
)

type Reason string

const (
	ReasonSpam       Reason = "spam"
	ReasonHarassment Reason = "harassment"
	ReasonViolence   Reason = "violence"
	ReasonAdult      Reason = "adult"
	ReasonCopyright  Reason = "copyright"
	ReasonOther      Reason = "other"
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusReviewing Status = "reviewing"
	StatusResolved  Status = "resolved"
	StatusDismissed Status = "dismissed"
)

type Resolution string

const (
	ResolutionWarn          Resolution = "warn"
	ResolutionDeleteContent Resolution = "delete_content"
	ResolutionSuspendUser   Resolution = "suspend_user"
	ResolutionBan           Resolution = "ban"
	ResolutionDismiss       Resolution = "dismiss"
)

// Snapshot 是 domain 与 persistence mapper 之间的无标签状态快照。
// 它不是 transport DTO，调用方只能通过 Report 行为产生新状态。
type Snapshot struct {
	ID          string
	Version     int64
	ReporterID  string
	TargetType  TargetType
	TargetID    string
	Reason      Reason
	Description string
	Status      Status
	ReviewerID  string
	Resolution  Resolution
	CreatedAt   time.Time
	UpdatedAt   time.Time
	ResolvedAt  *time.Time
}

type CreateParams struct {
	ID          string
	ReporterID  string
	TargetType  TargetType
	TargetID    string
	Reason      Reason
	Description string
	Now         time.Time
}

// Report 是手写行为聚合；状态字段保持私有，禁止 application 直接改写。
type Report struct {
	id          string
	version     int64
	reporterID  string
	targetType  TargetType
	targetID    string
	reason      Reason
	description string
	status      Status
	reviewerID  string
	resolution  Resolution
	createdAt   time.Time
	updatedAt   time.Time
	resolvedAt  *time.Time
}

func Create(params CreateParams) (*Report, error) {
	now := params.Now.UTC()
	if now.IsZero() {
		return nil, fmt.Errorf("%w: creation time is required", ErrInvalidReport)
	}
	report := &Report{
		id:          strings.TrimSpace(params.ID),
		version:     1,
		reporterID:  strings.TrimSpace(params.ReporterID),
		targetType:  params.TargetType,
		targetID:    strings.TrimSpace(params.TargetID),
		reason:      params.Reason,
		description: strings.TrimSpace(params.Description),
		status:      StatusPending,
		createdAt:   now,
		updatedAt:   now,
	}
	if err := report.validate(); err != nil {
		return nil, err
	}
	return report, nil
}

func Restore(snapshot Snapshot) (*Report, error) {
	report := &Report{
		id:          strings.TrimSpace(snapshot.ID),
		version:     snapshot.Version,
		reporterID:  strings.TrimSpace(snapshot.ReporterID),
		targetType:  snapshot.TargetType,
		targetID:    strings.TrimSpace(snapshot.TargetID),
		reason:      snapshot.Reason,
		description: strings.TrimSpace(snapshot.Description),
		status:      snapshot.Status,
		reviewerID:  strings.TrimSpace(snapshot.ReviewerID),
		resolution:  snapshot.Resolution,
		createdAt:   snapshot.CreatedAt.UTC(),
		updatedAt:   snapshot.UpdatedAt.UTC(),
		resolvedAt:  cloneTime(snapshot.ResolvedAt),
	}
	if err := report.validate(); err != nil {
		return nil, err
	}
	return report, nil
}

func (r *Report) BeginReview(reviewerID string, now time.Time) error {
	if r == nil || r.status != StatusPending {
		return fmt.Errorf("%w: only pending reports can begin review", ErrInvalidTransition)
	}
	reviewerID = strings.TrimSpace(reviewerID)
	if reviewerID == "" {
		return fmt.Errorf("%w: reviewer is required", ErrInvalidReport)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	r.status = StatusReviewing
	r.reviewerID = reviewerID
	return nil
}

func (r *Report) Resolve(
	reviewerID string,
	resolution Resolution,
	now time.Time,
) error {
	if resolution == ResolutionDismiss || !validResolution(resolution) {
		return fmt.Errorf("%w: resolution %q cannot resolve a report", ErrInvalidReport, resolution)
	}
	return r.close(reviewerID, resolution, StatusResolved, now)
}

func (r *Report) Dismiss(reviewerID string, now time.Time) error {
	return r.close(reviewerID, ResolutionDismiss, StatusDismissed, now)
}

func (r *Report) close(
	reviewerID string,
	resolution Resolution,
	status Status,
	now time.Time,
) error {
	if r == nil || r.status != StatusReviewing {
		return fmt.Errorf("%w: only reviewing reports can be closed", ErrInvalidTransition)
	}
	reviewerID = strings.TrimSpace(reviewerID)
	if reviewerID == "" {
		return fmt.Errorf("%w: reviewer is required", ErrInvalidReport)
	}
	if err := r.advance(now); err != nil {
		return err
	}
	resolvedAt := r.updatedAt
	r.status = status
	r.reviewerID = reviewerID
	r.resolution = resolution
	r.resolvedAt = &resolvedAt
	return nil
}

func (r *Report) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(r.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidReport)
	}
	r.version++
	r.updatedAt = now
	return nil
}

func (r *Report) ID() string {
	if r == nil {
		return ""
	}
	return r.id
}

func (r *Report) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}

func (r *Report) Status() Status {
	if r == nil {
		return ""
	}
	return r.status
}

func (r *Report) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:          r.id,
		Version:     r.version,
		ReporterID:  r.reporterID,
		TargetType:  r.targetType,
		TargetID:    r.targetID,
		Reason:      r.reason,
		Description: r.description,
		Status:      r.status,
		ReviewerID:  r.reviewerID,
		Resolution:  r.resolution,
		CreatedAt:   r.createdAt,
		UpdatedAt:   r.updatedAt,
		ResolvedAt:  cloneTime(r.resolvedAt),
	}
}

func (r *Report) validate() error {
	if r.id == "" ||
		r.version < 1 ||
		r.reporterID == "" ||
		!validTargetType(r.targetType) ||
		r.targetID == "" ||
		!validReason(r.reason) ||
		!validStatus(r.status) ||
		r.createdAt.IsZero() ||
		r.updatedAt.IsZero() ||
		r.updatedAt.Before(r.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidReport)
	}
	switch r.status {
	case StatusPending:
		if r.reviewerID != "" || r.resolution != "" || r.resolvedAt != nil {
			return fmt.Errorf("%w: pending report carries review state", ErrInvalidReport)
		}
	case StatusReviewing:
		if r.reviewerID == "" || r.resolution != "" || r.resolvedAt != nil {
			return fmt.Errorf("%w: reviewing state is inconsistent", ErrInvalidReport)
		}
	case StatusResolved:
		if r.reviewerID == "" ||
			!validResolution(r.resolution) ||
			r.resolution == ResolutionDismiss ||
			r.resolvedAt == nil {
			return fmt.Errorf("%w: resolved state is inconsistent", ErrInvalidReport)
		}
	case StatusDismissed:
		if r.reviewerID == "" ||
			r.resolution != ResolutionDismiss ||
			r.resolvedAt == nil {
			return fmt.Errorf("%w: dismissed state is inconsistent", ErrInvalidReport)
		}
	}
	return nil
}

func validTargetType(value TargetType) bool {
	switch value {
	case TargetPost, TargetComment, TargetUser, TargetCircle, TargetMessage:
		return true
	default:
		return false
	}
}

func validReason(value Reason) bool {
	switch value {
	case ReasonSpam, ReasonHarassment, ReasonViolence, ReasonAdult, ReasonCopyright, ReasonOther:
		return true
	default:
		return false
	}
}

func validStatus(value Status) bool {
	switch value {
	case StatusPending, StatusReviewing, StatusResolved, StatusDismissed:
		return true
	default:
		return false
	}
}

func validResolution(value Resolution) bool {
	switch value {
	case ResolutionWarn,
		ResolutionDeleteContent,
		ResolutionSuspendUser,
		ResolutionBan,
		ResolutionDismiss:
		return true
	default:
		return false
	}
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
