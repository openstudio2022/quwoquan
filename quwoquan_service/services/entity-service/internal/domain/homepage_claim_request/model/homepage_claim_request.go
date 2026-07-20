// Package model 包含 HomepageClaimRequest 聚合及其审核生命周期。
package model

import (
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidClaimRequest = errors.New("invalid homepage claim request")
	ErrInvalidClaimTier    = errors.New("invalid homepage claim tier")
	ErrClaimMaterial       = errors.New("homepage claim material is incomplete")
	ErrReviewerRequired    = errors.New("homepage claim reviewer account is required")
	ErrSelfReview          = errors.New("homepage claim requester cannot review own request")
	ErrAlreadyReviewed     = errors.New("homepage claim request is already reviewed")
	ErrInvalidReviewStatus = errors.New("invalid homepage claim review status")
)

type ClaimTier string

const (
	ClaimTierBasic    ClaimTier = "basic"
	ClaimTierVerified ClaimTier = "verified"
)

type Status string

const (
	StatusPendingReview Status = "pending_review"
	StatusApproved      Status = "approved"
	StatusRejected      Status = "rejected"
)

type Snapshot struct {
	ID                   string
	Version              int64
	HomepageID           string
	RequesterPersonaID   string
	ClaimTier            ClaimTier
	BusinessLicenseURL   string
	ContactPhone         string
	IdentityCardFrontURL string
	IdentityCardBackURL  string
	Note                 string
	Status               Status
	ReviewerAccountID    string
	ReviewNote           string
	CreatedAt            time.Time
	UpdatedAt            time.Time
	ReviewedAt           *time.Time
}

type CreateParams struct {
	ID                   string
	HomepageID           string
	RequesterPersonaID   string
	ClaimTier            ClaimTier
	BusinessLicenseURL   string
	ContactPhone         string
	IdentityCardFrontURL string
	IdentityCardBackURL  string
	Note                 string
	Now                  time.Time
}

type ReviewParams struct {
	ReviewerAccountID string
	TargetStatus      Status
	ReviewNote        string
	Now               time.Time
}

// HomepageClaimRequest 将可变状态保持私有；Homepage 的认领态由审核事件异步推进。
type HomepageClaimRequest struct {
	id                   string
	version              int64
	homepageID           string
	requesterPersonaID   string
	claimTier            ClaimTier
	businessLicenseURL   string
	contactPhone         string
	identityCardFrontURL string
	identityCardBackURL  string
	note                 string
	status               Status
	reviewerAccountID    string
	reviewNote           string
	createdAt            time.Time
	updatedAt            time.Time
	reviewedAt           *time.Time
}

func Create(params CreateParams) (*HomepageClaimRequest, error) {
	now := params.Now.UTC()
	request := &HomepageClaimRequest{
		id:                   strings.TrimSpace(params.ID),
		version:              1,
		homepageID:           strings.TrimSpace(params.HomepageID),
		requesterPersonaID:   strings.TrimSpace(params.RequesterPersonaID),
		claimTier:            ClaimTier(strings.TrimSpace(string(params.ClaimTier))),
		businessLicenseURL:   strings.TrimSpace(params.BusinessLicenseURL),
		contactPhone:         strings.TrimSpace(params.ContactPhone),
		identityCardFrontURL: strings.TrimSpace(params.IdentityCardFrontURL),
		identityCardBackURL:  strings.TrimSpace(params.IdentityCardBackURL),
		note:                 strings.TrimSpace(params.Note),
		status:               StatusPendingReview,
		createdAt:            now,
		updatedAt:            now,
	}
	if err := request.validate(); err != nil {
		return nil, err
	}
	return request, nil
}

func Restore(snapshot Snapshot) (*HomepageClaimRequest, error) {
	request := &HomepageClaimRequest{
		id:                   strings.TrimSpace(snapshot.ID),
		version:              snapshot.Version,
		homepageID:           strings.TrimSpace(snapshot.HomepageID),
		requesterPersonaID:   strings.TrimSpace(snapshot.RequesterPersonaID),
		claimTier:            ClaimTier(strings.TrimSpace(string(snapshot.ClaimTier))),
		businessLicenseURL:   strings.TrimSpace(snapshot.BusinessLicenseURL),
		contactPhone:         strings.TrimSpace(snapshot.ContactPhone),
		identityCardFrontURL: strings.TrimSpace(snapshot.IdentityCardFrontURL),
		identityCardBackURL:  strings.TrimSpace(snapshot.IdentityCardBackURL),
		note:                 strings.TrimSpace(snapshot.Note),
		status:               Status(strings.TrimSpace(string(snapshot.Status))),
		reviewerAccountID:    strings.TrimSpace(snapshot.ReviewerAccountID),
		reviewNote:           strings.TrimSpace(snapshot.ReviewNote),
		createdAt:            snapshot.CreatedAt.UTC(),
		updatedAt:            snapshot.UpdatedAt.UTC(),
		reviewedAt:           cloneTime(snapshot.ReviewedAt),
	}
	if err := request.validate(); err != nil {
		return nil, err
	}
	return request, nil
}

// Review 只允许 pending_review 进入一个终态。Facade 在调用前处理同目标终态 no-op。
func (r *HomepageClaimRequest) Review(params ReviewParams) error {
	if r == nil {
		return ErrInvalidClaimRequest
	}
	reviewerID := strings.TrimSpace(params.ReviewerAccountID)
	if reviewerID == "" {
		return ErrReviewerRequired
	}
	if reviewerID == r.requesterPersonaID {
		return ErrSelfReview
	}
	target := Status(strings.TrimSpace(string(params.TargetStatus)))
	if target != StatusApproved && target != StatusRejected {
		return ErrInvalidReviewStatus
	}
	if r.status != StatusPendingReview {
		return ErrAlreadyReviewed
	}
	now := params.Now.UTC()
	if now.IsZero() {
		return ErrInvalidClaimRequest
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

func (r *HomepageClaimRequest) validate() error {
	if r.id == "" || r.homepageID == "" || r.requesterPersonaID == "" ||
		r.version < 1 || r.createdAt.IsZero() || r.updatedAt.IsZero() {
		return ErrInvalidClaimRequest
	}
	if r.claimTier != ClaimTierBasic && r.claimTier != ClaimTierVerified {
		return ErrInvalidClaimTier
	}
	hasLicense := r.businessLicenseURL != ""
	hasIdentityFront := r.identityCardFrontURL != ""
	hasIdentityBack := r.identityCardBackURL != ""
	if r.contactPhone == "" || hasIdentityFront != hasIdentityBack {
		return ErrClaimMaterial
	}
	hasIdentityPair := hasIdentityFront && hasIdentityBack
	switch r.claimTier {
	case ClaimTierBasic:
		if !hasLicense && !hasIdentityPair {
			return ErrClaimMaterial
		}
	case ClaimTierVerified:
		if !hasLicense || !hasIdentityPair {
			return ErrClaimMaterial
		}
	}
	switch r.status {
	case StatusPendingReview:
		if r.reviewerAccountID != "" || r.reviewedAt != nil {
			return ErrInvalidClaimRequest
		}
	case StatusApproved, StatusRejected:
		if r.reviewerAccountID == "" || r.reviewerAccountID == r.requesterPersonaID ||
			r.reviewedAt == nil || r.reviewedAt.IsZero() {
			return ErrInvalidClaimRequest
		}
	default:
		return ErrInvalidReviewStatus
	}
	return nil
}

func (r *HomepageClaimRequest) ID() string {
	if r == nil {
		return ""
	}
	return r.id
}

func (r *HomepageClaimRequest) Version() int64 {
	if r == nil {
		return 0
	}
	return r.version
}

func (r *HomepageClaimRequest) Status() Status {
	if r == nil {
		return ""
	}
	return r.status
}

func (r *HomepageClaimRequest) Snapshot() Snapshot {
	if r == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:                   r.id,
		Version:              r.version,
		HomepageID:           r.homepageID,
		RequesterPersonaID:   r.requesterPersonaID,
		ClaimTier:            r.claimTier,
		BusinessLicenseURL:   r.businessLicenseURL,
		ContactPhone:         r.contactPhone,
		IdentityCardFrontURL: r.identityCardFrontURL,
		IdentityCardBackURL:  r.identityCardBackURL,
		Note:                 r.note,
		Status:               r.status,
		ReviewerAccountID:    r.reviewerAccountID,
		ReviewNote:           r.reviewNote,
		CreatedAt:            r.createdAt,
		UpdatedAt:            r.updatedAt,
		ReviewedAt:           cloneTime(r.reviewedAt),
	}
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
