package skillcontext

import (
	"context"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

type RunReader interface {
	Load(context.Context, string) (runruntime.Run, error)
}

type RuntimeResolver struct {
	ResolverRef   string
	Runs          RunReader
	Subscriptions subscriptionports.Store
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
	run, err := r.Runs.Load(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	switch strings.TrimSpace(r.ResolverRef) {
	case "trigger.envelope":
		return r.resolveTrigger(run)
	case "turn.slot":
		return resolveRunInput(run), nil
	case "turn.preferences":
		return resolveRunPreferences(run), nil
	case "subscription.plan":
		return r.resolveSubscription(ctx, run)
	case "user.interest_profile":
		return r.resolveInterests(ctx, run)
	default:
		return application.ResolvedContext{}, fmt.Errorf("unknown assistant context resolver")
	}
}

func (r RuntimeResolver) resolveTrigger(
	run runruntime.Run,
) (application.ResolvedContext, error) {
	triggerID := stringValue(run.Trigger, "triggerId")
	if triggerID == "" {
		return application.ResolvedContext{}, fmt.Errorf("assistant trigger envelope is unavailable")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, stringValue(run.Trigger, "occurredAt"))
	if err != nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant trigger occurredAt is invalid")
	}
	return application.ResolvedContext{
		Kind:        "trigger",
		SourceRef:   "trigger:" + triggerID,
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityInternal,
		CapturedAt:  occurredAt.UTC(),
		TokenCost:   64,
		Value: map[string]any{
			"kind":              stringValue(run.Trigger, "kind"),
			"triggerId":         triggerID,
			"occurredAt":        occurredAt.UTC().Format(time.RFC3339Nano),
			"subscriptionRef":   stringValue(run.Trigger, "subscriptionRef"),
			"signalRefs":        stringSliceValue(run.Trigger, "signalRefs"),
			"reason":            stringValue(run.Trigger, "reason"),
			"dedupeKey":         stringValue(run.Trigger, "dedupeKey"),
			"deliveryPolicyRef": stringValue(run.Trigger, "deliveryPolicyRef"),
		},
	}, nil
}

func resolveRunInput(run runruntime.Run) application.ResolvedContext {
	return application.ResolvedContext{
		Kind:        "conversation",
		SourceRef:   "run:" + run.RunID + ":input",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   approximateTokens(run.InputText),
		Value:       map[string]any{"text": strings.TrimSpace(run.InputText)},
	}
}

func resolveRunPreferences(run runruntime.Run) application.ResolvedContext {
	values := make([]map[string]any, 0, len(run.SessionPreferenceFacts)+len(run.LongTermPreferenceFacts))
	appendFacts := func(facts []preferencemodel.Snapshot) {
		for _, fact := range facts {
			values = append(values, map[string]any{
				"preferenceKey": string(fact.Kind),
				"value":         fact.Value,
			})
		}
	}
	appendFacts(run.SessionPreferenceFacts)
	appendFacts(run.LongTermPreferenceFacts)
	return application.ResolvedContext{
		Kind:        "memory",
		SourceRef:   "run:" + run.RunID + ":preferences",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   len(values) * 24,
		Value:       map[string]any{"preferences": values},
	}
}

func (r RuntimeResolver) resolveSubscription(
	ctx context.Context,
	run runruntime.Run,
) (application.ResolvedContext, error) {
	subscriptionRef := stringValue(run.Trigger, "subscriptionRef")
	if r.Subscriptions == nil || subscriptionRef == "" {
		return application.ResolvedContext{}, fmt.Errorf("assistant subscription context is unavailable")
	}
	subscription, err := r.Subscriptions.GetSkillSubscription(
		ctx,
		run.UserID,
		subscriptionRef,
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
	run runruntime.Run,
) (application.ResolvedContext, error) {
	if r.Interests == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant interest context is unavailable")
	}
	profile, err := r.Interests.GetInterestProfile(ctx, run.UserID)
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
		SourceRef:   "interest-profile:" + run.UserID,
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

func stringValue(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return strings.TrimSpace(value)
}

func stringSliceValue(values map[string]any, key string) []string {
	raw, ok := values[key].([]string)
	if ok {
		return append([]string(nil), raw...)
	}
	items, ok := values[key].([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		if value, ok := item.(string); ok && strings.TrimSpace(value) != "" {
			result = append(result, strings.TrimSpace(value))
		}
	}
	return result
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
	subscriptions subscriptionports.Store,
	interests ports.ProactiveInterestReader,
	extra ...application.RegisteredResolver,
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
	registered = append(registered, application.RegisteredResolver{
		ResolverRef: "conversation.current_context",
		Resolver: ConversationContextResolver{
			Runs: runs,
		},
	})
	registered = append(registered, extra...)
	return application.NewResolverRegistry(registered...)
}
