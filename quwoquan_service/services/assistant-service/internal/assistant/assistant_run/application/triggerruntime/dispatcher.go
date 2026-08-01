// Package triggerruntime converts proactive signals into the same canonical
// AssistantRun start request used by user-initiated work. It never renders
// proactive copy or executes Skill-specific branches.
package triggerruntime

import (
	"context"
	"errors"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Envelope struct {
	Kind              generated.AssistantTriggerKind
	TriggerID         string
	OccurredAt        time.Time
	SubscriptionRef   string
	SignalRefs        []string
	Reason            string
	DedupeKey         string
	DeliveryPolicyRef string
}

type SkillActivation struct {
	OwnerID                string
	SessionID              string
	SkillID                string
	Package                PackageReference
	ActivationProfileRef   string
	ContextProfileRef      string
	CapabilityProfileRef   string
	PresentationProfileRef string
	DeliveryPolicyRef      string
	UserInput              string
}

type RunStartRequest struct {
	OwnerID                string
	SessionID              string
	SkillID                string
	Package                PackageReference
	ActivationProfileRef   string
	ContextProfileRef      string
	CapabilityProfileRef   string
	PresentationProfileRef string
	Trigger                *Envelope
	UserInput              string
}

type PackageReference struct {
	PackageID      string
	PackageVersion string
	ReleaseDigest  string
}

type SubscriptionResolver interface {
	ResolveActivation(context.Context, string) (SkillActivation, error)
}

type TriggerAuthority interface {
	VerifyTrigger(context.Context, Envelope) error
}

type EligibilityPolicy interface {
	CheckDelivery(context.Context, SkillActivation, Envelope) error
}

type DedupeReservation interface {
	Commit(string) error
	Release()
}

type DedupeStore interface {
	Reserve(context.Context, string, time.Time) (DedupeReservation, error)
}

type RunStarter interface {
	StartRun(context.Context, RunStartRequest) (string, error)
}

type Dispatcher struct {
	subscriptions SubscriptionResolver
	authority     TriggerAuthority
	eligibility   EligibilityPolicy
	dedupe        DedupeStore
	runs          RunStarter
}

func NewDispatcher(
	subscriptions SubscriptionResolver,
	authority TriggerAuthority,
	eligibility EligibilityPolicy,
	dedupe DedupeStore,
	runs RunStarter,
) *Dispatcher {
	if subscriptions == nil || authority == nil || eligibility == nil || dedupe == nil || runs == nil {
		panic("assistant trigger dispatcher dependencies are required")
	}
	return &Dispatcher{
		subscriptions: subscriptions,
		authority:     authority,
		eligibility:   eligibility,
		dedupe:        dedupe,
		runs:          runs,
	}
}

func (d *Dispatcher) Dispatch(ctx context.Context, envelope Envelope) (string, error) {
	if err := validateEnvelope(envelope); err != nil {
		return "", err
	}
	if err := d.authority.VerifyTrigger(ctx, envelope); err != nil {
		return "", err
	}
	activation, err := d.subscriptions.ResolveActivation(ctx, envelope.SubscriptionRef)
	if err != nil {
		return "", err
	}
	if err := validateActivation(activation); err != nil {
		return "", err
	}
	if envelope.DeliveryPolicyRef != activation.DeliveryPolicyRef {
		return "", errors.New("trigger delivery policy does not match subscription")
	}
	if err := d.eligibility.CheckDelivery(ctx, activation, envelope); err != nil {
		return "", err
	}
	reservation, err := d.dedupe.Reserve(ctx, envelope.DedupeKey, envelope.OccurredAt)
	if err != nil {
		return "", err
	}
	committed := false
	defer func() {
		if !committed {
			reservation.Release()
		}
	}()
	request := RunStartRequest{
		OwnerID:                activation.OwnerID,
		SessionID:              activation.SessionID,
		SkillID:                activation.SkillID,
		Package:                activation.Package,
		ActivationProfileRef:   activation.ActivationProfileRef,
		ContextProfileRef:      activation.ContextProfileRef,
		CapabilityProfileRef:   activation.CapabilityProfileRef,
		PresentationProfileRef: activation.PresentationProfileRef,
		Trigger:                &envelope,
		UserInput:              strings.TrimSpace(activation.UserInput),
	}
	runID, err := d.runs.StartRun(ctx, request)
	if err != nil {
		return "", err
	}
	if strings.TrimSpace(runID) == "" {
		return "", errors.New("triggered assistant run returned no id")
	}
	if err := reservation.Commit(runID); err != nil {
		return "", err
	}
	committed = true
	return runID, nil
}

func validateEnvelope(envelope Envelope) error {
	if _, err := generated.ParseAssistantTriggerKind(envelope.Kind.WireName()); err != nil ||
		strings.TrimSpace(envelope.TriggerID) == "" || envelope.OccurredAt.IsZero() ||
		strings.TrimSpace(envelope.SubscriptionRef) == "" ||
		strings.TrimSpace(envelope.DedupeKey) == "" ||
		strings.TrimSpace(envelope.DeliveryPolicyRef) == "" {
		return errors.New("invalid assistant trigger envelope")
	}
	return nil
}

func validateActivation(activation SkillActivation) error {
	if strings.TrimSpace(activation.OwnerID) == "" || strings.TrimSpace(activation.SessionID) == "" ||
		strings.TrimSpace(activation.SkillID) == "" ||
		strings.TrimSpace(activation.Package.PackageID) == "" ||
		strings.TrimSpace(activation.Package.PackageVersion) == "" ||
		!canonicalDigest(activation.Package.ReleaseDigest) ||
		strings.TrimSpace(activation.ActivationProfileRef) == "" ||
		strings.TrimSpace(activation.ContextProfileRef) == "" ||
		strings.TrimSpace(activation.CapabilityProfileRef) == "" ||
		strings.TrimSpace(activation.PresentationProfileRef) == "" ||
		strings.TrimSpace(activation.DeliveryPolicyRef) == "" ||
		strings.TrimSpace(activation.UserInput) == "" {
		return errors.New("invalid assistant skill activation")
	}
	return nil
}

func canonicalDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) != len("sha256:")+64 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	for _, current := range strings.TrimPrefix(value, "sha256:") {
		if (current >= '0' && current <= '9') ||
			(current >= 'a' && current <= 'f') {
			continue
		}
		return false
	}
	return true
}
