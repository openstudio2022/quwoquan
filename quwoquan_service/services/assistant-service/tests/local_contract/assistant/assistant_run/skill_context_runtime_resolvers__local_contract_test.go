// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	runtimecontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

type skillContextRunReaderStub struct{ turn assistant.AssistantTurn }

func (s skillContextRunReaderStub) GetTurn(
	context.Context,
	string,
) (assistant.AssistantTurn, bool, error) {
	return s.turn, true, nil
}

type skillContextSubscriptionStub struct {
	ports.SkillSubscriptionStore
	subscription assistant.SkillSubscription
}

func (s skillContextSubscriptionStub) GetSkillSubscription(
	context.Context,
	string,
	string,
) (assistant.SkillSubscription, error) {
	return s.subscription, nil
}

type skillContextInterestStub struct{}

func (skillContextInterestStub) GetInterestProfile(
	context.Context,
	string,
) (*ports.ProactiveInterestProfile, error) {
	return &ports.ProactiveInterestProfile{
		TopInterests: []ports.ProactiveInterest{{TagRef: "Topic/旅行"}},
		Segments:     []string{"traveler"},
	}, nil
}

func TestProductionSkillContextResolversAssembleTrustedProactiveSnapshot(t *testing.T) {
	now := time.Now().UTC()
	turn := assistant.AssistantTurn{
		TurnID:    "run_context_1",
		UserID:    "user_1",
		CreatedAt: now.Add(-time.Minute),
		Trigger: assistant.AssistantTurnTrigger{Envelope: &assistant.AssistantTriggerEnvelope{
			Kind:              "schedule",
			TriggerID:         "trigger_1",
			OccurredAt:        now.Add(-time.Minute),
			SubscriptionRef:   "subscription_1",
			Reason:            "subscription_due",
			DedupeKey:         "delivery_1",
			DeliveryPolicyRef: "inherit_user_setting",
		}},
	}
	subscription := assistant.SkillSubscription{
		SubscriptionID: "subscription_1",
		SkillID:        "travel_journey_manager",
		DomainID:       "travel",
		SearchQueryPlan: assistant.SkillSubscriptionSearchQueryPlan{
			Queries: []string{"杭州天气", "西湖拥堵"},
		},
		Destination: assistant.SkillSubscriptionDestination{DestinationType: "user"},
		CreatedAt:   now.Add(-time.Hour),
	}
	registry, err := runtimecontext.NewRuntimeRegistry(
		skillContextRunReaderStub{turn: turn},
		skillContextSubscriptionStub{subscription: subscription},
		skillContextInterestStub{},
	)
	if err != nil {
		t.Fatal(err)
	}
	profile := application.Profile{
		ProfileID:   "context.proactive",
		AssetDigest: "sha256:test",
		Requirements: []application.Requirement{
			{
				SlotID: "trigger", Required: true, AcceptedSourceKinds: []string{"trigger"},
				Authority:   generated.AssistantContextAuthorityDomainCanonical,
				Sensitivity: generated.AssistantContextSensitivityInternal,
				Freshness:   time.Hour, TokenBudget: 256, ResolverRef: "trigger.envelope", FallbackPolicy: "block",
			},
			{
				SlotID: "subscription_plan", AcceptedSourceKinds: []string{"domain"},
				Authority:   generated.AssistantContextAuthorityUserDeclared,
				Sensitivity: generated.AssistantContextSensitivityPrivate,
				TokenBudget: 512, ResolverRef: "subscription.plan", FallbackPolicy: "omit",
			},
			{
				SlotID: "interest_profile", AcceptedSourceKinds: []string{"memory"},
				Authority:   generated.AssistantContextAuthorityDomainCanonical,
				Sensitivity: generated.AssistantContextSensitivityPrivate,
				TokenBudget: 256, ResolverRef: "user.interest_profile", FallbackPolicy: "omit",
			},
		},
	}
	snapshot, err := application.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		application.AssembleRequest{
			RunID: "run_context_1", SkillID: "travel_journey_manager",
			Visibility:         application.DeliveryPersonal,
			AllowedSensitivity: generated.AssistantContextSensitivityPrivate,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Segments) != 3 || len(snapshot.Missing) != 0 {
		t.Fatalf("snapshot=%+v", snapshot)
	}
	if snapshot.Segments[0].SourceRef != "trigger:trigger_1" || snapshot.Segments[1].SourceRef != "subscription:subscription_1" {
		t.Fatalf("source lineage=%+v", snapshot.Segments)
	}
}
