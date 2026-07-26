// Package model 包含 HomepageStatusReport 聚合及其审核生命周期。
package model

import (
	"errors"
	"net/url"
	"strings"
	"time"
)

var (
	ErrInvalidStatusReport = errors.New("invalid homepage status report")
	ErrInvalidReason       = errors.New("invalid homepage status report reason")
	ErrInvalidEvidenceURL  = errors.New("homepage status report evidence URL is invalid")
	ErrReviewerRequired    = errors.New("homepage status report reviewer account is required")
	ErrSelfReview          = errors.New("homepage status reporter cannot review own report")
	ErrAlreadyReviewed     = errors.New("homepage status report is already reviewed")
	ErrInvalidReviewStatus = errors.New("invalid homepage status report review status")
)

type Reason string

const (
	ReasonOffline        Reason = "offline"
	ReasonIncorrectInfo  Reason = "incorrect_info"
	ReasonDuplicateEntry Reason = "duplicate_entry"
	ReasonInactive       Reason = "inactive"
)

type Status string

const (
	StatusPendingReview    Status = "pending_review"
	StatusConfirmedOffline Status = "confirmed_offline"
	StatusDismissed        Status = "dismissed"
)

type Snapshot struct {
	ID                string
	Version           int64
	HomepageID        string
	ReporterPersonaID string
	Reason            Reason
	Description       string
	EvidenceURLs      []string
	Status            Status
	ReviewerAccountID string
	ReviewNote        string
	CreatedAt         time.Time
	UpdatedAt         time.Time
	ReviewedAt        *time.Time
}

type CreateParams struct {
	ID                string
	HomepageID        string
	ReporterPersonaID string
	Reason            Reason
	Description       string
	EvidenceURLs      []string
	Now               time.Time
}

type ReviewParams struct {
	ReviewerAccountID string
	TargetStatus      Status
	ReviewNote        string
	Now               time.Time
}

// HomepageStatusReport 的证据、上报人、原因与 homepageId 创建后均不可变。
type HomepageStatusReport struct {
	id                string
	version           int64
	homepageID        string
	reporterPersonaID string
	reason            Reason
	description       string
	evidenceURLs      []string
	status            Status
	reviewerAccountID string
	reviewNote        string
	createdAt         time.Time
	updatedAt         time.Time
	reviewedAt        *time.Time
}

func Create(params CreateParams) (*HomepageStatusReport, error) {
	now := params.Now.UTC()
	report := &HomepageStatusReport{
		id:                strings.TrimSpace(params.ID),
		version:           1,
		homepageID:        strings.TrimSpace(params.HomepageID),
		reporterPersonaID: strings.TrimSpace(params.ReporterPersonaID),
		reason:            Reason(strings.TrimSpace(string(params.Reason))),
		description:       strings.TrimSpace(params.Description),
		evidenceURLs:      normalizeStrings(params.EvidenceURLs),
		status:            StatusPendingReview,
		createdAt:         now,
		updatedAt:         now,
	}
	if err := report.validate(); err != nil {
		return nil, err
	}
	return report, nil
}

func Restore(snapshot Snapshot) (*HomepageStatusReport, error) {
	report := &HomepageStatusReport{
		id:                strings.TrimSpace(snapshot.ID),
		version:           snapshot.Version,
		homepageID:        strings.TrimSpace(snapshot.HomepageID),
		reporterPersonaID: strings.TrimSpace(snapshot.ReporterPersonaID),
		reason:            Reason(strings.TrimSpace(string(snapshot.Reason))),
		description:       strings.TrimSpace(snapshot.Description),
		evidenceURLs:      normalizeStrings(snapshot.EvidenceURLs),
		status:            Status(strings.TrimSpace(string(snapshot.Status))),
		reviewerAccountID: strings.TrimSpace(snapshot.ReviewerAccountID),
		reviewNote:        strings.TrimSpace(snapshot.ReviewNote),
		createdAt:         snapshot.CreatedAt.UTC(),
		updatedAt:         snapshot.UpdatedAt.UTC(),
		reviewedAt:        cloneTime(snapshot.ReviewedAt),
	}
	if err := report.validate(); err != nil {
		return nil, err
	}
	return report, nil
}

// Review 只允许 pending_review 进入一个终态。Facade 在调用前处理同目标终态 no-op。
func (r *HomepageStatusReport) Review(params ReviewParams) error {
	if r == nil {
		return ErrInvalidStatusReport
	}
	reviewerID := strings.TrimSpace(params.ReviewerAccountID)
	if reviewerID == "" {
		return ErrReviewerRequired
	}
	if reviewerID == r.reporterPersonaID {
		return ErrSelfReview
	}
	target := Status(strings.TrimSpace(string(params.TargetStatus)))
	if target != StatusConfirmedOffline && target != StatusDismissed {
		return ErrInvalidReviewStatus
	}
	if r.status != StatusPendingReview {
		return ErrAlreadyReviewed
	}
	now := params.Now.UTC()
	if now.IsZero() {
		return ErrInvalidStatusReport
	}
	if now.Before(r.updatedAt) {
		now = r.updatedAt
	}
	r.version++
	r.status = target
	r.reviewerAccountID = reviewerID
	r.reviewNote = strings.TrimSpace(params.ReviewNote)
	r.updatedAt = now
	r.reviewedAt = &now
	return r.validate()
}

func (r *HomepageStatusReport) validate() error {
	if r.id == "" || r.homepageID == "" || r.reporterPersonaID == "" ||
		r.version < 1 || r.createdAt.IsZero() || r.updatedAt.IsZero() {
		return ErrInvalidStatusReport
	}
	switch r.reason {
	case ReasonOffline, ReasonIncorrectInfo, ReasonDuplicateEntry, ReasonInactive:
	default:
		return ErrInvalidReason
	}
	for _, evidenceURL := range r.evidenceURLs {
		if !isCanonicalHTTPSURL(evidenceURL) {
			return ErrInvalidEvidenceURL
		}
	}
	switch r.status {
	case StatusPendingReview:
		if r.reviewerAccountID != "" || r.reviewedAt != nil {
			return ErrInvalidStatusReport
		}
	case StatusConfirmedOffline, StatusDismissed:
		if r.reviewerAccountID == "" || r.reviewerAccountID == r.reporterPersonaID ||
			r.reviewedAt == nil || r.reviewedAt.IsZero() {
			return ErrInvalidStatusReport
		}
	default:
		return ErrInvalidReviewStatus
	}
	return nil
}

func isCanonicalHTTPSURL(raw string) bool {
	parsed, err := url.ParseRequestURI(raw)
	return err == nil &&
		strings.EqualFold(parsed.Scheme, "https") &&
		parsed.Host != "" &&
		parsed.User == nil
}

func (r *HomepageStatusReport) ID() string {
	if r == nil {
		return ""
	}
	return r.id
}

func (r *HomepageStatusReport) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}

func (r *HomepageStatusReport) Status() Status {
	if r == nil {
		return ""
	}
	return r.status
}

func (r *HomepageStatusReport) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:                r.id,
		Version:           r.version,
		HomepageID:        r.homepageID,
		ReporterPersonaID: r.reporterPersonaID,
		Reason:            r.reason,
		Description:       r.description,
		EvidenceURLs:      append([]string(nil), r.evidenceURLs...),
		Status:            r.status,
		ReviewerAccountID: r.reviewerAccountID,
		ReviewNote:        r.reviewNote,
		CreatedAt:         r.createdAt,
		UpdatedAt:         r.updatedAt,
		ReviewedAt:        cloneTime(r.reviewedAt),
	}
}

func normalizeStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}
	normalized := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, found := seen[value]; found {
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	if len(normalized) == 0 {
		return nil
	}
	return normalized
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
