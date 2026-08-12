package application

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/domain"
)

var ErrAssignmentStateUnavailable = errors.New("rollout assignment state unavailable")

type AssignmentStore interface {
	IsCandidate(context.Context, string, string) (bool, error)
	AssignCandidate(context.Context, string, string, time.Duration) error
	Ping(context.Context) error
}

type Subject struct {
	DeviceActorID string
	AccountID     string
	Platform      string
	AppVersion    string
	AppBuild      string
	Region        string
	Carrier       string
}

type Decision struct {
	Target        domain.Target
	Bucket        int
	Reason        string
	SubjectDigest string
}

type Evaluator struct {
	policy        domain.Policy
	allocationKey []byte
	store         AssignmentStore
	assignmentTTL time.Duration
}

// Stage returns the policy stage used for this process-local decision. Disabled,
// completed and rolled-back campaigns intentionally share the inactive value.
func (evaluator *Evaluator) Stage() string {
	if evaluator == nil || !evaluator.policy.Enabled ||
		evaluator.policy.Status == "rolled_back" || evaluator.policy.Status == "complete" {
		return "inactive"
	}
	if stage := strings.TrimSpace(evaluator.policy.Stage); stage != "" {
		return stage
	}
	return "unknown"
}

func NewEvaluator(
	policy domain.Policy,
	allocationKey []byte,
	store AssignmentStore,
	assignmentTTL time.Duration,
) (*Evaluator, error) {
	if err := policy.Validate(); err != nil {
		return nil, err
	}
	if !policy.Enabled {
		return &Evaluator{policy: policy}, nil
	}
	if len(allocationKey) < 32 {
		return nil, errors.New("rollout allocation key must contain at least 32 bytes")
	}
	if store == nil {
		return nil, errors.New("rollout assignment store is required")
	}
	if assignmentTTL <= 0 {
		return nil, errors.New("rollout assignment TTL must be positive")
	}
	return &Evaluator{
		policy: policy, allocationKey: append([]byte(nil), allocationKey...),
		store: store, assignmentTTL: assignmentTTL,
	}, nil
}

func (evaluator *Evaluator) Decide(ctx context.Context, subject Subject) (Decision, error) {
	if evaluator == nil || !evaluator.policy.Enabled ||
		evaluator.policy.Status == "rolled_back" || evaluator.policy.Status == "complete" {
		return Decision{Target: domain.TargetStable, Reason: "campaign_inactive"}, nil
	}
	deviceActorID := strings.TrimSpace(subject.DeviceActorID)
	if deviceActorID == "" {
		return Decision{Target: domain.TargetStable, Reason: "missing_rollout_subject"}, nil
	}
	subjectDigest, err := domain.SubjectDigest(
		evaluator.allocationKey, evaluator.policy.CampaignID, deviceActorID,
	)
	if err != nil {
		return Decision{}, err
	}
	existing, err := evaluator.store.IsCandidate(
		ctx, evaluator.policy.CampaignID, subjectDigest,
	)
	if err != nil {
		return Decision{}, fmt.Errorf("%w: read candidate assignment: %v", ErrAssignmentStateUnavailable, err)
	}
	if existing {
		return Decision{
			Target: domain.TargetCandidate, Reason: "existing_assignment", SubjectDigest: subjectDigest,
		}, nil
	}

	bucket, err := domain.Bucket(
		evaluator.allocationKey, evaluator.policy, subject.Platform, deviceActorID,
	)
	if err != nil {
		return Decision{}, err
	}
	stage := evaluator.policy.Stages[evaluator.policy.Stage]
	whitelisted := contains(evaluator.policy.InternalCanary.AccountIDs, subject.AccountID) ||
		contains(evaluator.policy.InternalCanary.DeviceActorIDs, deviceActorID)
	eligible := stage.AudienceMatches(
		strings.TrimSpace(subject.Platform), strings.TrimSpace(subject.AppVersion),
		strings.TrimSpace(subject.Region), strings.TrimSpace(subject.Carrier),
	)
	candidate := whitelisted || (eligible && bucket < stage.BasisPoints)
	if !candidate {
		reason := "bucket_outside_threshold"
		if !eligible {
			reason = "audience_not_eligible"
		}
		return Decision{
			Target: domain.TargetStable, Bucket: bucket, Reason: reason, SubjectDigest: subjectDigest,
		}, nil
	}
	if err := evaluator.store.AssignCandidate(
		ctx, evaluator.policy.CampaignID, subjectDigest, evaluator.assignmentTTL,
	); err != nil {
		return Decision{}, fmt.Errorf("%w: persist candidate assignment: %v", ErrAssignmentStateUnavailable, err)
	}
	reason := "percentage_threshold"
	if whitelisted {
		reason = "internal_canary"
	}
	return Decision{
		Target: domain.TargetCandidate, Bucket: bucket, Reason: reason, SubjectDigest: subjectDigest,
	}, nil
}

func (evaluator *Evaluator) Ready(ctx context.Context) error {
	if evaluator == nil || !evaluator.policy.Enabled ||
		evaluator.policy.Status == "rolled_back" || evaluator.policy.Status == "complete" {
		return nil
	}
	if err := evaluator.store.Ping(ctx); err != nil {
		return fmt.Errorf("%w: %v", ErrAssignmentStateUnavailable, err)
	}
	return nil
}

func contains(values []string, target string) bool {
	target = strings.TrimSpace(target)
	for _, value := range values {
		if strings.TrimSpace(value) == target && target != "" {
			return true
		}
	}
	return false
}
