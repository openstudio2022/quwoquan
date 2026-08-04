// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-context-proactive-runtime/spec.md#gwt-001
package assistant_run_test

import (
	"context"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	runtimecontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

type skillContextRunReaderStub struct{ run runruntime.Run }

func (s skillContextRunReaderStub) Load(
	context.Context,
	string,
) (runruntime.Run, error) {
	return s.run, nil
}

type skillContextSubscriptionStub struct {
	subscriptionports.Store
	subscription skillmodel.SkillSubscription
}

func (s skillContextSubscriptionStub) GetSkillSubscription(
	context.Context,
	string,
	string,
) (skillmodel.SkillSubscription, error) {
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
	run := runruntime.Run{
		RunID:     "run_context_1",
		UserID:    "user_1",
		CreatedAt: now.Add(-time.Minute),
		InputText: "安排杭州行程",
		Trigger: map[string]any{
			"kind":              "schedule",
			"triggerId":         "trigger_1",
			"occurredAt":        now.Add(-time.Minute).Format(time.RFC3339Nano),
			"subscriptionRef":   "subscription_1",
			"reason":            "subscription_due",
			"dedupeKey":         "delivery_1",
			"deliveryPolicyRef": "inherit_user_setting",
		},
		SessionPreferences: []preferencemodel.AssistantPreferenceSnapshot{{
			Kind:  preferencemodel.KindLanguage,
			Value: "zh-CN",
		}},
	}
	subscription := skillmodel.SkillSubscription{
		SubscriptionID: "subscription_1",
		SkillID:        "travel_companion",
		DomainID:       "travel",
		SearchQueryPlan: skillmodel.SkillSubscriptionSearchQueryPlan{
			Queries: []string{"杭州天气", "西湖拥堵"},
		},
		Destination: skillmodel.SkillSubscriptionDestination{DestinationType: "user"},
		CreatedAt:   now.Add(-time.Hour),
	}
	descriptors, err := runtimecontext.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	registry, err := runtimecontext.NewRuntimeRegistry(
		catalog,
		skillContextRunReaderStub{run: run},
		skillContextSubscriptionStub{subscription: subscription},
		skillContextInterestStub{},
	)
	if err != nil {
		t.Fatal(err)
	}
	profile := application.Profile{
		ProfileID: "context.proactive",
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
	profile.AssetDigest = canonicalFixtureDigest(profile)
	snapshot, err := application.NewAssembler(registry).Assemble(
		context.Background(),
		profile,
		application.AssembleRequest{
			RunID: "run_context_1", SkillID: "travel_companion",
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
