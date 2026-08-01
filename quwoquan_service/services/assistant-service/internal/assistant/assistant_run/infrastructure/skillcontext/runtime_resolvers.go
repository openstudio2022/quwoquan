package skillcontext

import (
	"context"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

type RunReader interface {
	GetTurn(context.Context, string) (assistant.AssistantTurn, bool, error)
}

type RuntimeResolver struct {
	ResolverRef   string
	Runs          RunReader
	Subscriptions ports.SkillSubscriptionStore
	Interests     ports.ProactiveInterestReader
	Now           func() time.Time
}

func (r RuntimeResolver) Resolve(
	ctx context.Context,
	request application.ResolveRequest,
) (application.ResolvedContext, error) {
	if r.Runs == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant run reader is unavailable")
	}
	turn, found, err := r.Runs.GetTurn(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	if !found {
		return application.ResolvedContext{}, fmt.Errorf("assistant run is unavailable")
	}
	switch strings.TrimSpace(r.ResolverRef) {
	case "trigger.envelope":
		return r.resolveTrigger(turn)
	case "turn.slot":
		return resolveTurnInput(turn), nil
	case "turn.preferences":
		return resolveTurnPreferences(turn), nil
	case "subscription.plan":
		return r.resolveSubscription(ctx, turn)
	case "user.interest_profile":
		return r.resolveInterests(ctx, turn)
	default:
		return application.ResolvedContext{}, fmt.Errorf("unknown assistant context resolver")
	}
}

func (r RuntimeResolver) resolveTrigger(
	turn assistant.AssistantTurn,
) (application.ResolvedContext, error) {
	envelope := turn.Trigger.Envelope
	if envelope == nil || strings.TrimSpace(envelope.TriggerID) == "" {
		return application.ResolvedContext{}, fmt.Errorf("assistant trigger envelope is unavailable")
	}
	return application.ResolvedContext{
		Kind:        "trigger",
		SourceRef:   "trigger:" + envelope.TriggerID,
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityInternal,
		CapturedAt:  envelope.OccurredAt.UTC(),
		TokenCost:   64,
		Value: map[string]any{
			"kind":              envelope.Kind,
			"triggerId":         envelope.TriggerID,
			"occurredAt":        envelope.OccurredAt.UTC().Format(time.RFC3339Nano),
			"subscriptionRef":   envelope.SubscriptionRef,
			"signalRefs":        append([]string(nil), envelope.SignalRefs...),
			"reason":            envelope.Reason,
			"dedupeKey":         envelope.DedupeKey,
			"deliveryPolicyRef": envelope.DeliveryPolicyRef,
		},
	}, nil
}

func resolveTurnInput(turn assistant.AssistantTurn) application.ResolvedContext {
	return application.ResolvedContext{
		Kind:        "conversation",
		SourceRef:   "run:" + turn.TurnID + ":input",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  turn.CreatedAt.UTC(),
		TokenCost:   approximateTokens(turn.Input.Text),
		Value:       map[string]any{"text": strings.TrimSpace(turn.Input.Text)},
	}
}

func resolveTurnPreferences(turn assistant.AssistantTurn) application.ResolvedContext {
	values := make([]map[string]any, 0, len(turn.SessionPreferenceFacts)+len(turn.LongTermPreferenceFacts))
	appendFacts := func(facts []preferencemodel.Snapshot) {
		for _, fact := range facts {
			values = append(values, map[string]any{
				"preferenceKey": string(fact.Kind),
				"value":         fact.Value,
			})
		}
	}
	appendFacts(turn.SessionPreferenceFacts)
	appendFacts(turn.LongTermPreferenceFacts)
	return application.ResolvedContext{
		Kind:        "memory",
		SourceRef:   "run:" + turn.TurnID + ":preferences",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  turn.CreatedAt.UTC(),
		TokenCost:   len(values) * 24,
		Value:       map[string]any{"preferences": values},
	}
}

func (r RuntimeResolver) resolveSubscription(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (application.ResolvedContext, error) {
	if r.Subscriptions == nil || turn.Trigger.Envelope == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant subscription context is unavailable")
	}
	subscription, err := r.Subscriptions.GetSkillSubscription(
		ctx,
		turn.UserID,
		turn.Trigger.Envelope.SubscriptionRef,
	)
	if err != nil {
		return application.ResolvedContext{}, err
	}
	return application.ResolvedContext{
		Kind:        "domain",
		SourceRef:   "subscription:" + subscription.SubscriptionID,
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  subscription.CreatedAt.UTC(),
		TokenCost:   128,
		Value: map[string]any{
			"skillId":     subscription.SkillID,
			"domainId":    subscription.DomainID,
			"tagRefs":     append([]string(nil), subscription.TagRefs...),
			"queries":     append([]string(nil), subscription.SearchQueryPlan.Queries...),
			"rawText":     subscription.SearchQueryPlan.RawText,
			"destination": string(subscription.Destination.DestinationType),
		},
	}, nil
}

func (r RuntimeResolver) resolveInterests(
	ctx context.Context,
	turn assistant.AssistantTurn,
) (application.ResolvedContext, error) {
	if r.Interests == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant interest context is unavailable")
	}
	profile, err := r.Interests.GetInterestProfile(ctx, turn.UserID)
	if err != nil {
		return application.ResolvedContext{}, err
	}
	if profile == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant interest context is unavailable")
	}
	tags := make([]string, 0, len(profile.TopInterests))
	for _, interest := range profile.TopInterests {
		if tag := strings.TrimSpace(interest.TagRef); tag != "" {
			tags = append(tags, tag)
		}
	}
	now := time.Now
	if r.Now != nil {
		now = r.Now
	}
	return application.ResolvedContext{
		Kind:        "memory",
		SourceRef:   "interest-profile:" + turn.UserID,
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  now().UTC(),
		TokenCost:   len(tags)*8 + len(profile.Segments)*8,
		Value: map[string]any{
			"tagRefs":        tags,
			"segments":       append([]string(nil), profile.Segments...),
			"lifecycleStage": strings.TrimSpace(profile.LifecycleStage),
		},
	}, nil
}

func approximateTokens(value string) int {
	runes := len([]rune(strings.TrimSpace(value)))
	if runes == 0 {
		return 0
	}
	return (runes + 3) / 4
}

func NewRuntimeRegistry(
	runs RunReader,
	subscriptions ports.SkillSubscriptionStore,
	interests ports.ProactiveInterestReader,
) (*application.ResolverRegistry, error) {
	refs := []string{
		"trigger.envelope",
		"turn.slot",
		"turn.preferences",
		"subscription.plan",
		"user.interest_profile",
	}
	registered := make([]application.RegisteredResolver, 0, len(refs))
	for _, ref := range refs {
		registered = append(registered, application.RegisteredResolver{
			ResolverRef: ref,
			Resolver: RuntimeResolver{
				ResolverRef:   ref,
				Runs:          runs,
				Subscriptions: subscriptions,
				Interests:     interests,
			},
		})
	}
	return application.NewResolverRegistry(registered...)
}
