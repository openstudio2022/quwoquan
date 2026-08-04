package model

import (
	"encoding/base64"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalidArgument = errors.New("skill activity request is invalid")
	ErrUnavailable     = errors.New("skill activity source is unavailable")
)

const (
	KindRun          ActivityKind = "run"
	KindConsent      ActivityKind = "consent"
	KindSubscription ActivityKind = "subscription"
	KindDataControl  ActivityKind = "data_control"

	RecoveryRetryRun           RecoveryAction = "retry_run"
	RecoveryProvideInput       RecoveryAction = "provide_input"
	RecoveryReviewApproval     RecoveryAction = "review_approval"
	RecoveryResumeRun          RecoveryAction = "resume_run"
	RecoveryReviewConsent      RecoveryAction = "review_consent"
	RecoveryManageConsent      RecoveryAction = "manage_consent"
	RecoveryResumeSubscription RecoveryAction = "resume_subscription"
	RecoveryManageSubscription RecoveryAction = "manage_subscription"
	RecoveryRetryDataControl   RecoveryAction = "retry_data_control"

	DisplayRunAccepted                    DisplayKey = "assistant.skill_activity.run.accepted"
	DisplayRunOrienting                   DisplayKey = "assistant.skill_activity.run.orienting"
	DisplayRunPlanning                    DisplayKey = "assistant.skill_activity.run.planning"
	DisplayRunExecuting                   DisplayKey = "assistant.skill_activity.run.executing"
	DisplayRunObserving                   DisplayKey = "assistant.skill_activity.run.observing"
	DisplayRunReflecting                  DisplayKey = "assistant.skill_activity.run.reflecting"
	DisplayRunCheckpointing               DisplayKey = "assistant.skill_activity.run.checkpointing"
	DisplayRunWaitingUser                 DisplayKey = "assistant.skill_activity.run.waiting_user"
	DisplayRunWaitingApproval             DisplayKey = "assistant.skill_activity.run.waiting_approval"
	DisplayRunWaitingExternal             DisplayKey = "assistant.skill_activity.run.waiting_external"
	DisplayRunPaused                      DisplayKey = "assistant.skill_activity.run.paused"
	DisplayRunSynthesizing                DisplayKey = "assistant.skill_activity.run.synthesizing"
	DisplayRunVerifying                   DisplayKey = "assistant.skill_activity.run.verifying"
	DisplayRunCompleted                   DisplayKey = "assistant.skill_activity.run.completed"
	DisplayRunFailed                      DisplayKey = "assistant.skill_activity.run.failed"
	DisplayRunCancelled                   DisplayKey = "assistant.skill_activity.run.cancelled"
	DisplayConsentGranted                 DisplayKey = "assistant.skill_activity.consent.granted"
	DisplayConsentRevoked                 DisplayKey = "assistant.skill_activity.consent.revoked"
	DisplaySubscriptionActive             DisplayKey = "assistant.skill_activity.subscription.active"
	DisplaySubscriptionPaused             DisplayKey = "assistant.skill_activity.subscription.paused"
	DisplaySubscriptionArchived           DisplayKey = "assistant.skill_activity.subscription.archived"
	DisplayDataControlPendingConfirmation DisplayKey = "assistant.skill_activity.data_control.pending_confirmation"
	DisplayDataControlExecuting           DisplayKey = "assistant.skill_activity.data_control.executing"
	DisplayDataControlCompleted           DisplayKey = "assistant.skill_activity.data_control.completed"
	DisplayDataControlCancelled           DisplayKey = "assistant.skill_activity.data_control.cancelled"
	DisplayDataControlFailed              DisplayKey = "assistant.skill_activity.data_control.failed"
)

type ActivityKind string
type RecoveryAction string
type DisplayKey string

type Semantics struct {
	DisplayKey     DisplayKey
	RecoveryAction RecoveryAction
}

type Item struct {
	ActivityID           string         `json:"activityId" bson:"_id"`
	AccountID            string         `json:"-" bson:"accountId"`
	SkillID              string         `json:"skillId" bson:"skillId"`
	ActivityKind         ActivityKind   `json:"activityKind" bson:"activityKind"`
	Status               string         `json:"status" bson:"status"`
	DisplayKey           DisplayKey     `json:"displayKey" bson:"displayKey"`
	SourceObjectRef      string         `json:"sourceObjectRef" bson:"sourceObjectRef"`
	SourceRevision       int64          `json:"sourceRevision" bson:"sourceRevision"`
	RunID                string         `json:"-" bson:"runId,omitempty"`
	ConsentID            string         `json:"-" bson:"consentId,omitempty"`
	SubscriptionID       string         `json:"-" bson:"subscriptionId,omitempty"`
	DataControlRequestID string         `json:"dataControlRequestId,omitempty" bson:"dataControlRequestId,omitempty"`
	FailureCode          string         `json:"failureCode,omitempty" bson:"failureCode,omitempty"`
	RecoveryAction       RecoveryAction `json:"recoveryAction,omitempty" bson:"recoveryAction,omitempty"`
	OccurredAt           time.Time      `json:"occurredAt" bson:"occurredAt"`
}

type ExternalSource struct {
	SourceKind   string `json:"sourceKind"`
	OperationRef string `json:"operationRef"`
}

type Slice struct {
	Items           []Item           `json:"items"`
	NextCursor      string           `json:"nextCursor,omitempty"`
	ExternalSources []ExternalSource `json:"externalSources"`
}

type Cursor struct {
	OccurredAt time.Time
	ActivityID string
}

func (item Item) Validate() error {
	if strings.TrimSpace(item.ActivityID) == "" ||
		strings.TrimSpace(item.AccountID) == "" ||
		strings.TrimSpace(item.SkillID) == "" ||
		strings.TrimSpace(string(item.ActivityKind)) == "" ||
		strings.TrimSpace(item.Status) == "" ||
		strings.TrimSpace(string(item.DisplayKey)) == "" ||
		strings.TrimSpace(item.SourceObjectRef) == "" ||
		item.SourceRevision < 0 || item.OccurredAt.IsZero() {
		return ErrInvalidArgument
	}
	semantics, err := ResolveSemantics(item.ActivityKind, item.Status)
	if err != nil || item.DisplayKey != semantics.DisplayKey ||
		item.RecoveryAction != semantics.RecoveryAction {
		return ErrInvalidArgument
	}
	return nil
}

// ResolveSemantics is the single closed projection from owner state to the
// user-facing Skill activity semantic key and recovery intent. It deliberately
// rejects unknown owner states instead of manufacturing localization keys.
func ResolveSemantics(kind ActivityKind, rawStatus string) (Semantics, error) {
	status := strings.TrimSpace(rawStatus)
	switch kind {
	case KindRun:
		switch status {
		case "accepted":
			return Semantics{DisplayKey: DisplayRunAccepted}, nil
		case "orienting":
			return Semantics{DisplayKey: DisplayRunOrienting}, nil
		case "planning":
			return Semantics{DisplayKey: DisplayRunPlanning}, nil
		case "executing":
			return Semantics{DisplayKey: DisplayRunExecuting}, nil
		case "observing":
			return Semantics{DisplayKey: DisplayRunObserving}, nil
		case "reflecting":
			return Semantics{DisplayKey: DisplayRunReflecting}, nil
		case "checkpointing":
			return Semantics{DisplayKey: DisplayRunCheckpointing}, nil
		case "waiting_user":
			return Semantics{DisplayKey: DisplayRunWaitingUser, RecoveryAction: RecoveryProvideInput}, nil
		case "waiting_approval":
			return Semantics{DisplayKey: DisplayRunWaitingApproval, RecoveryAction: RecoveryReviewApproval}, nil
		case "waiting_external":
			return Semantics{DisplayKey: DisplayRunWaitingExternal}, nil
		case "paused":
			return Semantics{DisplayKey: DisplayRunPaused, RecoveryAction: RecoveryResumeRun}, nil
		case "synthesizing":
			return Semantics{DisplayKey: DisplayRunSynthesizing}, nil
		case "verifying":
			return Semantics{DisplayKey: DisplayRunVerifying}, nil
		case "completed":
			return Semantics{DisplayKey: DisplayRunCompleted}, nil
		case "failed":
			return Semantics{DisplayKey: DisplayRunFailed, RecoveryAction: RecoveryRetryRun}, nil
		case "cancelled":
			return Semantics{DisplayKey: DisplayRunCancelled}, nil
		}
	case KindConsent:
		switch status {
		case "granted":
			return Semantics{DisplayKey: DisplayConsentGranted, RecoveryAction: RecoveryManageConsent}, nil
		case "revoked":
			return Semantics{DisplayKey: DisplayConsentRevoked, RecoveryAction: RecoveryReviewConsent}, nil
		}
	case KindSubscription:
		switch status {
		case "active":
			return Semantics{DisplayKey: DisplaySubscriptionActive, RecoveryAction: RecoveryManageSubscription}, nil
		case "paused":
			return Semantics{DisplayKey: DisplaySubscriptionPaused, RecoveryAction: RecoveryResumeSubscription}, nil
		case "archived":
			return Semantics{DisplayKey: DisplaySubscriptionArchived}, nil
		}
	case KindDataControl:
		switch status {
		case "pending_confirmation":
			return Semantics{DisplayKey: DisplayDataControlPendingConfirmation}, nil
		case "executing":
			return Semantics{DisplayKey: DisplayDataControlExecuting}, nil
		case "completed":
			return Semantics{DisplayKey: DisplayDataControlCompleted}, nil
		case "cancelled":
			return Semantics{DisplayKey: DisplayDataControlCancelled}, nil
		case "failed":
			return Semantics{DisplayKey: DisplayDataControlFailed, RecoveryAction: RecoveryRetryDataControl}, nil
		}
	}
	return Semantics{}, ErrInvalidArgument
}

func Sort(items []Item) {
	sort.SliceStable(items, func(left, right int) bool {
		if items[left].OccurredAt.Equal(items[right].OccurredAt) {
			return items[left].ActivityID > items[right].ActivityID
		}
		return items[left].OccurredAt.After(items[right].OccurredAt)
	})
}

func EncodeCursor(item Item) string {
	raw := item.OccurredAt.UTC().Format(time.RFC3339Nano) + "\x1f" + item.ActivityID
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

func ParseCursor(value string) (*Cursor, error) {
	value = strings.TrimSpace(value)
	if value == "" {
		return nil, nil
	}
	raw, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil {
		return nil, ErrInvalidArgument
	}
	parts := strings.SplitN(string(raw), "\x1f", 2)
	if len(parts) != 2 || strings.TrimSpace(parts[1]) == "" {
		return nil, ErrInvalidArgument
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return nil, ErrInvalidArgument
	}
	return &Cursor{OccurredAt: occurredAt.UTC(), ActivityID: parts[1]}, nil
}

func StableID(kind ActivityKind, sourceRef string, revision int64) string {
	return fmt.Sprintf("%s:%s:%d", strings.TrimSpace(string(kind)), strings.TrimSpace(sourceRef), revision)
}
