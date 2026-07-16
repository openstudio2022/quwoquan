package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidPostModerationCase           = errors.New("invalid post moderation case")
	ErrInvalidPostModerationCaseTransition = errors.New("invalid post moderation case transition")
	ErrReviewerForbidden                   = errors.New("post moderation reviewer forbidden")
)

type Status string

const (
	StatusPending    Status = "pending"
	StatusReviewed   Status = "reviewed"
	StatusApproved   Status = "approved"
	StatusRejected   Status = "rejected"
	StatusSuperseded Status = "superseded"
)

type Decision string

const (
	DecisionApprove Decision = "approved"
	DecisionReject  Decision = "rejected"
)

// Snapshot is the persistence boundary for PostModerationCase. The case binds
// approval to both the Post version and canonical content digest.
type Snapshot struct {
	ID             string
	Version        int64
	PostID         string
	PostVersion    int64
	ContentDigest  string
	Status         Status
	ReviewerID     string
	DecisionReason string
	CreatedAt      time.Time
	UpdatedAt      time.Time
	DecidedAt      *time.Time
}

type OpenParams struct {
	ID            string
	PostID        string
	PostVersion   int64
	ContentDigest string
	Now           time.Time
}

// PostModerationCase is an independent review aggregate. Post owns neither
// this state nor the approval decision; it can only ask the eligibility reader.
type PostModerationCase struct {
	id             string
	version        int64
	postID         string
	postVersion    int64
	contentDigest  string
	status         Status
	reviewerID     string
	decisionReason string
	createdAt      time.Time
	updatedAt      time.Time
	decidedAt      *time.Time
}

func Open(params OpenParams) (*PostModerationCase, error) {
	now := params.Now.UTC()
	caseItem := &PostModerationCase{
		id:            strings.TrimSpace(params.ID),
		version:       1,
		postID:        strings.TrimSpace(params.PostID),
		postVersion:   params.PostVersion,
		contentDigest: normalizeDigest(params.ContentDigest),
		status:        StatusPending,
		createdAt:     now,
		updatedAt:     now,
	}
	if err := caseItem.validate(); err != nil {
		return nil, err
	}
	return caseItem, nil
}

func Restore(snapshot Snapshot) (*PostModerationCase, error) {
	caseItem := &PostModerationCase{
		id:             strings.TrimSpace(snapshot.ID),
		version:        snapshot.Version,
		postID:         strings.TrimSpace(snapshot.PostID),
		postVersion:    snapshot.PostVersion,
		contentDigest:  normalizeDigest(snapshot.ContentDigest),
		status:         snapshot.Status,
		reviewerID:     strings.TrimSpace(snapshot.ReviewerID),
		decisionReason: strings.TrimSpace(snapshot.DecisionReason),
		createdAt:      snapshot.CreatedAt.UTC(),
		updatedAt:      snapshot.UpdatedAt.UTC(),
		decidedAt:      cloneTime(snapshot.DecidedAt),
	}
	if err := caseItem.validate(); err != nil {
		return nil, err
	}
	return caseItem, nil
}

func (c *PostModerationCase) Review(reviewerID string, now time.Time) error {
	if c == nil || c.status != StatusPending {
		return fmt.Errorf("%w: only pending cases can be reviewed", ErrInvalidPostModerationCaseTransition)
	}
	reviewerID = strings.TrimSpace(reviewerID)
	if reviewerID == "" {
		return fmt.Errorf("%w: reviewer is required", ErrInvalidPostModerationCase)
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.status = StatusReviewed
	c.reviewerID = reviewerID
	return nil
}

func (c *PostModerationCase) Decide(
	reviewerID string,
	decision Decision,
	reason string,
	now time.Time,
) error {
	if c == nil || c.status != StatusReviewed {
		return fmt.Errorf("%w: only reviewed cases can be decided", ErrInvalidPostModerationCaseTransition)
	}
	reviewerID = strings.TrimSpace(reviewerID)
	if reviewerID == "" || reviewerID != c.reviewerID {
		return fmt.Errorf("%w: reviewer does not own this review", ErrReviewerForbidden)
	}
	if decision != DecisionApprove && decision != DecisionReject {
		return fmt.Errorf("%w: decision is invalid", ErrInvalidPostModerationCase)
	}
	reason = strings.TrimSpace(reason)
	if reason == "" {
		return fmt.Errorf("%w: decision reason is required", ErrInvalidPostModerationCase)
	}
	if err := c.advance(now); err != nil {
		return err
	}
	if decision == DecisionApprove {
		c.status = StatusApproved
	} else {
		c.status = StatusRejected
	}
	c.decisionReason = reason
	decidedAt := c.updatedAt
	c.decidedAt = &decidedAt
	return nil
}

func (c *PostModerationCase) Supersede(now time.Time) error {
	if c == nil || c.status == StatusSuperseded {
		return fmt.Errorf("%w: superseded case cannot transition", ErrInvalidPostModerationCaseTransition)
	}
	if err := c.advance(now); err != nil {
		return err
	}
	c.status = StatusSuperseded
	return nil
}

// IsPublicationEligible returns true only for the exact approved revision.
// Any post edit changes at least postVersion or contentDigest and invalidates
// eligibility without requiring Post to duplicate moderation lifecycle state.
func (c *PostModerationCase) IsPublicationEligible(
	postID string,
	postVersion int64,
	contentDigest string,
) bool {
	if c == nil {
		return false
	}
	return c.status == StatusApproved &&
		c.postID == strings.TrimSpace(postID) &&
		c.postVersion == postVersion &&
		c.contentDigest == normalizeDigest(contentDigest)
}

func (c *PostModerationCase) ID() string {
	if c == nil {
		return ""
	}
	return c.id
}

func (c *PostModerationCase) Version() int64 {
	if c == nil {
		return 0
	}
	return c.version
}

func (c *PostModerationCase) PostID() string {
	if c == nil {
		return ""
	}
	return c.postID
}

func (c *PostModerationCase) PostVersion() int64 {
	if c == nil {
		return 0
	}
	return c.postVersion
}

func (c *PostModerationCase) ContentDigest() string {
	if c == nil {
		return ""
	}
	return c.contentDigest
}

func (c *PostModerationCase) Status() Status {
	if c == nil {
		return ""
	}
	return c.status
}

func (c *PostModerationCase) ReviewerID() string {
	if c == nil {
		return ""
	}
	return c.reviewerID
}

func (c *PostModerationCase) Snapshot() Snapshot {
	if c == nil {
		return Snapshot{}
	}
	return Snapshot{
		ID:             c.id,
		Version:        c.version,
		PostID:         c.postID,
		PostVersion:    c.postVersion,
		ContentDigest:  c.contentDigest,
		Status:         c.status,
		ReviewerID:     c.reviewerID,
		DecisionReason: c.decisionReason,
		CreatedAt:      c.createdAt,
		UpdatedAt:      c.updatedAt,
		DecidedAt:      cloneTime(c.decidedAt),
	}
}

func (c *PostModerationCase) validate() error {
	if c == nil ||
		c.id == "" ||
		c.version < 1 ||
		c.postID == "" ||
		c.postVersion < 1 ||
		c.contentDigest == "" ||
		!validStatus(c.status) ||
		c.createdAt.IsZero() ||
		c.updatedAt.IsZero() ||
		c.updatedAt.Before(c.createdAt) {
		return fmt.Errorf("%w: required state is missing", ErrInvalidPostModerationCase)
	}
	switch c.status {
	case StatusPending:
		if c.reviewerID != "" || c.decisionReason != "" || c.decidedAt != nil {
			return fmt.Errorf("%w: pending case carries review state", ErrInvalidPostModerationCase)
		}
	case StatusReviewed:
		if c.reviewerID == "" || c.decisionReason != "" || c.decidedAt != nil {
			return fmt.Errorf("%w: reviewed case state is inconsistent", ErrInvalidPostModerationCase)
		}
	case StatusApproved, StatusRejected:
		if c.reviewerID == "" || c.decisionReason == "" || c.decidedAt == nil {
			return fmt.Errorf("%w: decided case state is inconsistent", ErrInvalidPostModerationCase)
		}
	case StatusSuperseded:
		if c.status == StatusSuperseded && c.reviewerID == "" && c.decisionReason != "" {
			return fmt.Errorf("%w: superseded case carries an orphan decision", ErrInvalidPostModerationCase)
		}
	}
	return nil
}

func (c *PostModerationCase) advance(now time.Time) error {
	now = now.UTC()
	if now.IsZero() || now.Before(c.updatedAt) {
		return fmt.Errorf("%w: transition time is invalid", ErrInvalidPostModerationCase)
	}
	c.version++
	c.updatedAt = now
	return nil
}

func validStatus(value Status) bool {
	switch value {
	case StatusPending, StatusReviewed, StatusApproved, StatusRejected, StatusSuperseded:
		return true
	default:
		return false
	}
}

func normalizeDigest(value string) string {
	return strings.ToLower(strings.TrimSpace(value))
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
