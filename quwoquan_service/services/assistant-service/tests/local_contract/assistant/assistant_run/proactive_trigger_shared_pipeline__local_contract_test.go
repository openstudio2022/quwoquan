// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	triggerruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/triggerruntime"
)

type subscriptionResolverStub struct {
	activation triggerruntime.SkillActivation
}

func (s subscriptionResolverStub) ResolveActivation(
	context.Context,
	string,
) (triggerruntime.SkillActivation, error) {
	return s.activation, nil
}

type triggerAuthorityStub struct{ reject bool }

func (s triggerAuthorityStub) VerifyTrigger(context.Context, triggerruntime.Envelope) error {
	if s.reject {
		return errors.New("untrusted signal")
	}
	return nil
}

type eligibilityStub struct{ reject bool }

func (s eligibilityStub) CheckDelivery(
	context.Context,
	triggerruntime.SkillActivation,
	triggerruntime.Envelope,
) error {
	if s.reject {
		return errors.New("quiet hours")
	}
	return nil
}

type dedupeStoreStub struct{ reservation *dedupeReservationSpy }

func (s dedupeStoreStub) Reserve(
	context.Context,
	string,
	time.Time,
) (triggerruntime.DedupeReservation, error) {
	return s.reservation, nil
}

type dedupeReservationSpy struct {
	runID    string
	released bool
}

func (s *dedupeReservationSpy) Commit(runID string) error { s.runID = runID; return nil }
func (s *dedupeReservationSpy) Release()                  { s.released = true }

type runStarterSpy struct {
	requests []triggerruntime.RunStartRequest
}

func (s *runStarterSpy) StartRun(
	_ context.Context,
	request triggerruntime.RunStartRequest,
) (string, error) {
	s.requests = append(s.requests, request)
	return "run_triggered", nil
}

func TestProactiveTriggerStartsCanonicalRunWithoutSchedulerAuthoredContent(t *testing.T) {
	activation := triggerruntime.SkillActivation{
		OwnerID:                "user_1",
		SessionID:              "session_proactive",
		SkillID:                "travel",
		Package:                testTriggerPackageReference(),
		ActivationProfileRef:   "asset:travel-activation",
		ContextProfileRef:      "asset:travel-context",
		CapabilityProfileRef:   "asset:travel-capability",
		PresentationProfileRef: "asset:travel-presentation",
		DeliveryPolicyRef:      "delivery:personal",
		UserInput:              "检查我的旅行风险",
	}
	reservation := &dedupeReservationSpy{}
	runs := &runStarterSpy{}
	dispatcher := triggerruntime.NewDispatcher(
		subscriptionResolverStub{activation: activation},
		triggerAuthorityStub{},
		eligibilityStub{},
		dedupeStoreStub{reservation: reservation},
		runs,
	)
	envelope := triggerruntime.Envelope{
		Kind:              generated.AssistantTriggerKindSchedule,
		TriggerID:         "trigger_1",
		OccurredAt:        time.Now().UTC(),
		SubscriptionRef:   "subscription_1",
		DedupeKey:         "travel:2026-07-31",
		DeliveryPolicyRef: "delivery:personal",
	}
	runID, err := dispatcher.Dispatch(context.Background(), envelope)
	if err != nil {
		t.Fatalf("Dispatch() error = %v", err)
	}
	if runID != "run_triggered" || reservation.runID != runID || reservation.released {
		t.Fatalf("dispatch result = run %q reservation %#v", runID, reservation)
	}
	if len(runs.requests) != 1 {
		t.Fatalf("run requests = %#v", runs.requests)
	}
	request := runs.requests[0]
	if request.UserInput != activation.UserInput || request.Trigger == nil ||
		request.SkillID != "travel" ||
		request.Package != activation.Package ||
		request.ContextProfileRef != activation.ContextProfileRef ||
		request.PresentationProfileRef != activation.PresentationProfileRef {
		t.Fatalf("canonical run request = %#v", request)
	}
}

func TestProactiveTriggerFailsBeforeRunForAuthorityEligibilityOrPolicyMismatch(t *testing.T) {
	baseActivation := triggerruntime.SkillActivation{
		OwnerID:                "user_1",
		SessionID:              "session_1",
		SkillID:                "travel",
		Package:                testTriggerPackageReference(),
		ActivationProfileRef:   "activation",
		ContextProfileRef:      "context",
		CapabilityProfileRef:   "capability",
		PresentationProfileRef: "presentation",
		DeliveryPolicyRef:      "delivery:personal",
		UserInput:              "检查我的旅行风险",
	}
	baseEnvelope := triggerruntime.Envelope{
		Kind:              generated.AssistantTriggerKindEvent,
		TriggerID:         "trigger_1",
		OccurredAt:        time.Now().UTC(),
		SubscriptionRef:   "subscription_1",
		DedupeKey:         "event:1",
		DeliveryPolicyRef: "delivery:personal",
	}
	tests := []struct {
		name        string
		authority   triggerAuthorityStub
		eligibility eligibilityStub
		activation  triggerruntime.SkillActivation
		envelope    triggerruntime.Envelope
	}{
		{name: "untrusted trigger", authority: triggerAuthorityStub{reject: true}, activation: baseActivation, envelope: baseEnvelope},
		{name: "quiet hours", eligibility: eligibilityStub{reject: true}, activation: baseActivation, envelope: baseEnvelope},
		{name: "policy mismatch", activation: baseActivation, envelope: func() triggerruntime.Envelope {
			value := baseEnvelope
			value.DeliveryPolicyRef = "delivery:public"
			return value
		}()},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			runs := &runStarterSpy{}
			reservation := &dedupeReservationSpy{}
			dispatcher := triggerruntime.NewDispatcher(
				subscriptionResolverStub{activation: test.activation},
				test.authority,
				test.eligibility,
				dedupeStoreStub{reservation: reservation},
				runs,
			)
			if _, err := dispatcher.Dispatch(context.Background(), test.envelope); err == nil {
				t.Fatal("Dispatch() unexpectedly succeeded")
			}
			if len(runs.requests) != 0 || reservation.runID != "" {
				t.Fatalf("run or dedupe committed: %#v %#v", runs.requests, reservation)
			}
		})
	}
}

func TestEveryProactiveTriggerKindUsesTheSameCanonicalRunStarter(t *testing.T) {
	kinds := []generated.AssistantTriggerKind{
		generated.AssistantTriggerKindSchedule,
		generated.AssistantTriggerKindEvent,
		generated.AssistantTriggerKindContextChange,
		generated.AssistantTriggerKindFollowUp,
	}
	for _, kind := range kinds {
		t.Run(kind.WireName(), func(t *testing.T) {
			reservation := &dedupeReservationSpy{}
			runs := &runStarterSpy{}
			dispatcher := triggerruntime.NewDispatcher(
				subscriptionResolverStub{activation: triggerruntime.SkillActivation{
					OwnerID:                "user_1",
					SessionID:              "session_1",
					SkillID:                "travel",
					Package:                testTriggerPackageReference(),
					ActivationProfileRef:   "activation",
					ContextProfileRef:      "context",
					CapabilityProfileRef:   "capability",
					PresentationProfileRef: "presentation",
					DeliveryPolicyRef:      "delivery:personal",
					UserInput:              "检查我的旅行风险",
				}},
				triggerAuthorityStub{},
				eligibilityStub{},
				dedupeStoreStub{reservation: reservation},
				runs,
			)
			_, err := dispatcher.Dispatch(context.Background(), triggerruntime.Envelope{
				Kind:              kind,
				TriggerID:         "trigger_" + kind.WireName(),
				OccurredAt:        time.Now().UTC(),
				SubscriptionRef:   "subscription_1",
				DedupeKey:         "dedupe:" + kind.WireName(),
				DeliveryPolicyRef: "delivery:personal",
			})
			if err != nil {
				t.Fatal(err)
			}
			if len(runs.requests) != 1 ||
				runs.requests[0].UserInput != "检查我的旅行风险" ||
				runs.requests[0].Trigger == nil {
				t.Fatalf("kind %s bypassed canonical run request: %#v", kind, runs.requests)
			}
		})
	}
}

func testTriggerPackageReference() triggerruntime.PackageReference {
	return triggerruntime.PackageReference{
		PackageID:      "assistant.session.skills",
		PackageVersion: "1.0.0",
		ReleaseDigest:  "sha256:" + strings.Repeat("a", 64),
	}
}
