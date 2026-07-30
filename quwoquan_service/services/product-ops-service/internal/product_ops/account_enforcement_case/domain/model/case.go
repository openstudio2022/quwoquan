// Package model owns the Product Ops account-enforcement case invariants.
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalidArgument        = errors.New("account enforcement case invalid argument")
	ErrCaseNotFound           = errors.New("account enforcement case not found")
	ErrVersionConflict        = errors.New("account enforcement case version conflict")
	ErrIdempotencyConflict    = errors.New("account enforcement command idempotency conflict")
	ErrCaseClosed             = errors.New("account enforcement case closed")
	ErrReviewConflict         = errors.New("account enforcement review conflict")
	ErrSourceDecisionConflict = errors.New("account enforcement source decision conflict")
	ErrDeliveryNotRecoverable = errors.New("account enforcement delivery is not recoverable")
)

type CaseKind string

const (
	CaseKindModeration CaseKind = "moderation"
	CaseKindAppeal     CaseKind = "appeal"
)

type CaseStatus string

const (
	CaseStatusPendingApproval CaseStatus = "pending_approval"
	CaseStatusApproved        CaseStatus = "approved"
	CaseStatusRejected        CaseStatus = "rejected"
)

type ReviewVerdict string

const (
	ReviewVerdictApprove ReviewVerdict = "approve"
	ReviewVerdictReject  ReviewVerdict = "reject"
)

type EnforcementAction string

const (
	EnforcementActionSuspend EnforcementAction = "suspend"
	EnforcementActionRestore EnforcementAction = "restore"
)

type DeliveryStatus string

const (
	DeliveryStatusPending    DeliveryStatus = "pending"
	DeliveryStatusRetrying   DeliveryStatus = "retrying"
	DeliveryStatusDelivered  DeliveryStatus = "delivered"
	DeliveryStatusDeadLetter DeliveryStatus = "dead_letter"
)

type Case struct {
	ID               string
	Kind             CaseKind
	AccountID        string
	Status           CaseStatus
	PolicyRef        string
	SourceDecisionID string
	IntakeRef        string
	EvidenceRefs     []string
	OpenedBy         string
	Version          int64
	OpenedAt         time.Time
	UpdatedAt        time.Time
	Reviews          []Review
	Decision         *Decision
	DeliveryStatus   DeliveryStatus
}

type Review struct {
	ReviewerID string
	Verdict    ReviewVerdict
	ReviewedAt time.Time
}

type Decision struct {
	ID             string
	CaseID         string
	AccountID      string
	Action         EnforcementAction
	CaseRef        string
	DecisionDigest string
	ApprovedAt     time.Time
}

type OpenModerationParams struct {
	CaseID       string
	AccountID    string
	PolicyRef    string
	EvidenceRefs []string
	OpenedBy     string
	OpenedAt     time.Time
}

type OpenAppealParams struct {
	CaseID           string
	AccountID        string
	SourceDecisionID string
	IntakeRef        string
	EvidenceRefs     []string
	OpenedBy         string
	OpenedAt         time.Time
}

func OpenModeration(params OpenModerationParams) (Case, error) {
	now := params.OpenedAt.UTC()
	current := Case{
		ID:           strings.TrimSpace(params.CaseID),
		Kind:         CaseKindModeration,
		AccountID:    strings.TrimSpace(params.AccountID),
		Status:       CaseStatusPendingApproval,
		PolicyRef:    strings.TrimSpace(params.PolicyRef),
		EvidenceRefs: normalizeRefs(params.EvidenceRefs),
		OpenedBy:     strings.TrimSpace(params.OpenedBy),
		Version:      1,
		OpenedAt:     now,
		UpdatedAt:    now,
	}
	if err := current.Validate(); err != nil || current.PolicyRef == "" {
		return Case{}, ErrInvalidArgument
	}
	return current, nil
}

func OpenAppeal(params OpenAppealParams) (Case, error) {
	now := params.OpenedAt.UTC()
	current := Case{
		ID:               strings.TrimSpace(params.CaseID),
		Kind:             CaseKindAppeal,
		AccountID:        strings.TrimSpace(params.AccountID),
		Status:           CaseStatusPendingApproval,
		SourceDecisionID: strings.TrimSpace(params.SourceDecisionID),
		IntakeRef:        strings.TrimSpace(params.IntakeRef),
		EvidenceRefs:     normalizeRefs(params.EvidenceRefs),
		OpenedBy:         strings.TrimSpace(params.OpenedBy),
		Version:          1,
		OpenedAt:         now,
		UpdatedAt:        now,
	}
	if err := current.Validate(); err != nil ||
		current.SourceDecisionID == "" || current.IntakeRef == "" {
		return Case{}, ErrInvalidArgument
	}
	return current, nil
}

func (current Case) Review(
	reviewerID string,
	verdict ReviewVerdict,
	reviewedAt time.Time,
) (Case, Review, *Decision, error) {
	reviewerID = strings.TrimSpace(reviewerID)
	if current.Status != CaseStatusPendingApproval {
		return Case{}, Review{}, nil, ErrCaseClosed
	}
	if !validOpaque(reviewerID, 160) ||
		(verdict != ReviewVerdictApprove && verdict != ReviewVerdictReject) ||
		reviewedAt.IsZero() {
		return Case{}, Review{}, nil, ErrInvalidArgument
	}
	for _, existing := range current.Reviews {
		if existing.ReviewerID == reviewerID {
			return Case{}, Review{}, nil, ErrReviewConflict
		}
	}

	review := Review{
		ReviewerID: reviewerID,
		Verdict:    verdict,
		ReviewedAt: reviewedAt.UTC(),
	}
	next := current
	next.Reviews = append(append([]Review(nil), current.Reviews...), review)
	next.Version++
	next.UpdatedAt = review.ReviewedAt

	if verdict == ReviewVerdictReject {
		next.Status = CaseStatusRejected
		return next, review, nil, nil
	}
	if approvalCount(next.Reviews) < 2 {
		return next, review, nil, nil
	}

	next.Status = CaseStatusApproved
	decision := next.issueDecision(review.ReviewedAt)
	next.Decision = &decision
	next.DeliveryStatus = DeliveryStatusPending
	return next, review, &decision, nil
}

func (current Case) Validate() error {
	if !validOpaque(current.ID, 128) || !validOpaque(current.AccountID, 128) ||
		!validOpaque(current.OpenedBy, 160) || current.Version <= 0 ||
		current.OpenedAt.IsZero() || current.UpdatedAt.IsZero() ||
		current.Status == "" || len(current.EvidenceRefs) == 0 ||
		len(current.EvidenceRefs) > 32 {
		return ErrInvalidArgument
	}
	for _, ref := range current.EvidenceRefs {
		if !validOpaque(ref, 256) {
			return ErrInvalidArgument
		}
	}
	switch current.Kind {
	case CaseKindModeration:
		if !validOpaque(current.PolicyRef, 256) ||
			current.SourceDecisionID != "" || current.IntakeRef != "" {
			return ErrInvalidArgument
		}
	case CaseKindAppeal:
		if !validOpaque(current.SourceDecisionID, 128) ||
			!validOpaque(current.IntakeRef, 256) || current.PolicyRef != "" {
			return ErrInvalidArgument
		}
	default:
		return ErrInvalidArgument
	}
	return nil
}

func (current Case) issueDecision(approvedAt time.Time) Decision {
	action := EnforcementActionSuspend
	if current.Kind == CaseKindAppeal {
		action = EnforcementActionRestore
	}
	idSeed := digest(struct {
		Schema  string `json:"schema"`
		CaseID  string `json:"caseId"`
		Version int64  `json:"version"`
		Action  string `json:"action"`
	}{
		Schema:  "account_enforcement_decision_id",
		CaseID:  current.ID,
		Version: current.Version,
		Action:  string(action),
	})
	decisionID := "aed_" + idSeed
	caseRef := "ops.account_enforcement_case/" + current.ID
	reviewers := approvedReviewers(current.Reviews)
	decisionDigest := digest(struct {
		Schema            string   `json:"schema"`
		DecisionID        string   `json:"decisionId"`
		CaseRef           string   `json:"caseRef"`
		CaseFingerprint   string   `json:"caseFingerprint"`
		AccountID         string   `json:"accountId"`
		Action            string   `json:"action"`
		ApprovedReviewers []string `json:"approvedReviewers"`
		ApprovedAt        string   `json:"approvedAt"`
	}{
		Schema:            "account_enforcement_decision",
		DecisionID:        decisionID,
		CaseRef:           caseRef,
		CaseFingerprint:   current.Fingerprint(),
		AccountID:         current.AccountID,
		Action:            string(action),
		ApprovedReviewers: reviewers,
		ApprovedAt:        approvedAt.UTC().Format(time.RFC3339Nano),
	})
	return Decision{
		ID:             decisionID,
		CaseID:         current.ID,
		AccountID:      current.AccountID,
		Action:         action,
		CaseRef:        caseRef,
		DecisionDigest: decisionDigest,
		ApprovedAt:     approvedAt.UTC(),
	}
}

func (current Case) Fingerprint() string {
	refs := append([]string(nil), current.EvidenceRefs...)
	sort.Strings(refs)
	return digest(struct {
		Schema           string   `json:"schema"`
		CaseID           string   `json:"caseId"`
		Kind             string   `json:"kind"`
		AccountID        string   `json:"accountId"`
		PolicyRef        string   `json:"policyRef,omitempty"`
		SourceDecisionID string   `json:"sourceDecisionId,omitempty"`
		IntakeRef        string   `json:"intakeRef,omitempty"`
		EvidenceRefs     []string `json:"evidenceRefs"`
	}{
		Schema:           "account_enforcement_case",
		CaseID:           current.ID,
		Kind:             string(current.Kind),
		AccountID:        current.AccountID,
		PolicyRef:        current.PolicyRef,
		SourceDecisionID: current.SourceDecisionID,
		IntakeRef:        current.IntakeRef,
		EvidenceRefs:     refs,
	})
}

func approvalCount(reviews []Review) int {
	return len(approvedReviewers(reviews))
}

func approvedReviewers(reviews []Review) []string {
	values := make([]string, 0, len(reviews))
	for _, review := range reviews {
		if review.Verdict == ReviewVerdictApprove {
			values = append(values, review.ReviewerID)
		}
	}
	sort.Strings(values)
	return values
}

func normalizeRefs(values []string) []string {
	out := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

func validOpaque(value string, max int) bool {
	value = strings.TrimSpace(value)
	if value == "" || len(value) > max {
		return false
	}
	for _, current := range value {
		if current < 0x20 || current == 0x7f {
			return false
		}
	}
	return true
}

func digest(value any) string {
	payload, _ := json.Marshal(value)
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}
