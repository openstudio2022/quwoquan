package skillcontext

import (
	"context"
	"fmt"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	preferencemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

type RunReader interface {
	Load(context.Context, string) (runruntime.Run, error)
}

type RuntimeResolver struct {
	Runs    RunReader
	Project func(context.Context, runruntime.Run) (application.ResolvedContext, error)
}

func (r RuntimeResolver) Resolve(
	ctx context.Context,
	request application.ResolveRequest,
) (application.ResolvedContext, error) {
	if r.Runs == nil || r.Project == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant run reader is unavailable")
	}
	run, err := r.Runs.Load(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	return r.Project(ctx, run)
}

func resolveTrigger(
	_ context.Context,
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

func resolveRunInput(
	_ context.Context,
	run runruntime.Run,
) (application.ResolvedContext, error) {
	return application.ResolvedContext{
		Kind:        "conversation",
		SourceRef:   "run:" + run.RunID + ":input",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   approximateTokens(run.InputText),
		Value:       map[string]any{"text": strings.TrimSpace(run.InputText)},
	}, nil
}

func resolveRunPreferences(
	_ context.Context,
	run runruntime.Run,
) (application.ResolvedContext, error) {
	values := make([]map[string]any, 0, len(run.SessionPreferences)+len(run.LongTermPreferences))
	appendPreferences := func(preferences []preferencemodel.AssistantPreferenceSnapshot) {
		for _, preference := range preferences {
			values = append(values, map[string]any{
				"preferenceKey": string(preference.Kind),
				"value":         preference.Value,
			})
		}
	}
	appendPreferences(run.SessionPreferences)
	appendPreferences(run.LongTermPreferences)
	return application.ResolvedContext{
		Kind:        "memory",
		SourceRef:   "run:" + run.RunID + ":preferences",
		Authority:   generated.AssistantContextAuthorityUserDeclared,
		Sensitivity: generated.AssistantContextSensitivityPrivate,
		CapturedAt:  run.CreatedAt.UTC(),
		TokenCost:   len(values) * 24,
		Value:       map[string]any{"preferences": values},
	}, nil
}

func resolveSubscription(
	ctx context.Context,
	run runruntime.Run,
	subscriptions subscriptionports.Store,
) (application.ResolvedContext, error) {
	subscriptionRef := stringValue(run.Trigger, "subscriptionRef")
	if subscriptions == nil || subscriptionRef == "" {
		return application.ResolvedContext{}, fmt.Errorf("assistant subscription context is unavailable")
	}
	subscription, err := subscriptions.GetSkillSubscription(
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

func resolveInterests(
	ctx context.Context,
	run runruntime.Run,
	interests ports.ProactiveInterestReader,
	now func() time.Time,
) (application.ResolvedContext, error) {
	if interests == nil {
		return application.ResolvedContext{}, fmt.Errorf("assistant interest context is unavailable")
	}
	profile, err := interests.GetInterestProfile(ctx, run.UserID)
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
	if now == nil {
		now = time.Now
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
	descriptors readerports.Catalog,
	runs RunReader,
	subscriptions subscriptionports.Store,
	interests ports.ProactiveInterestReader,
	extra ...application.RegisteredResolver,
) (*application.ResolverRegistry, error) {
	projections := []struct {
		ResolverRef string
		Project     func(context.Context, runruntime.Run) (application.ResolvedContext, error)
	}{
		{ResolverRef: "trigger.envelope", Project: resolveTrigger},
		{ResolverRef: "turn.slot", Project: resolveRunInput},
		{ResolverRef: "turn.preferences", Project: resolveRunPreferences},
		{ResolverRef: feedbackcontext.ResolverRef, Project: resolveFeedbackContext},
		{
			ResolverRef: "subscription.plan",
			Project: func(ctx context.Context, run runruntime.Run) (application.ResolvedContext, error) {
				return resolveSubscription(ctx, run, subscriptions)
			},
		},
		{
			ResolverRef: "user.interest_profile",
			Project: func(ctx context.Context, run runruntime.Run) (application.ResolvedContext, error) {
				return resolveInterests(ctx, run, interests, nil)
			},
		},
	}
	registered := make([]application.RegisteredResolver, 0, len(projections)+1+len(extra))
	for _, projection := range projections {
		registered = append(registered, application.RegisteredResolver{
			ResolverRef: projection.ResolverRef,
			Resolver: RuntimeResolver{
				Runs:    runs,
				Project: projection.Project,
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
	return application.NewResolverRegistry(descriptors, registered...)
}

// NewRuntimeRegistryWithCanonicalReaders is the production assembly boundary:
// every canonical object Reader is registered into the same immutable runtime
// registry as the built-in and additional object-owned resolvers.
func NewRuntimeRegistryWithCanonicalReaders(
	descriptors readerports.Catalog,
	runs RunReader,
	subscriptions subscriptionports.Store,
	interests ports.ProactiveInterestReader,
	readers domainreader.CanonicalReaders,
	extra ...application.RegisteredResolver,
) (*application.ResolverRegistry, error) {
	canonical, err := NewCanonicalDomainResolverRegistrations(runs, readers)
	if err != nil {
		return nil, err
	}
	registered := make([]application.RegisteredResolver, 0, len(canonical)+len(extra))
	registered = append(registered, canonical...)
	registered = append(registered, extra...)
	return NewRuntimeRegistry(
		descriptors,
		runs,
		subscriptions,
		interests,
		registered...,
	)
}
