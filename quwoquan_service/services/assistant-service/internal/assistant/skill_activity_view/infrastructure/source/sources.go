package source

import (
	"context"
	"regexp"
	"strings"

	runruntime "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	activityapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/application"
	activitymodel "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/model"
	consentmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/model"
	datacontrolmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

var safeFailureCode = regexp.MustCompile(`^[A-Za-z0-9_.:-]{1,160}$`)

type RunReader interface {
	ListSkillActivityEvents(context.Context, string, string, int) ([]runruntime.SkillActivityEvent, error)
}

type ConsentReader interface {
	ListSkillConsentEvents(context.Context, string, string, int) ([]consentmodel.Event, error)
}

type SubscriptionReader interface {
	ListSkillSubscriptionActivities(context.Context, string, string, int) ([]subscriptionmodel.ActivityEvent, error)
}

type DataControlReader interface {
	ListSkillDataControlActivities(context.Context, string, string, int) ([]datacontrolmodel.ActivityEvent, error)
}

type RunSource struct{ reader RunReader }
type ConsentSource struct{ reader ConsentReader }
type SubscriptionSource struct{ reader SubscriptionReader }
type DataControlSource struct{ reader DataControlReader }

var (
	_ activityapplication.Source = RunSource{}
	_ activityapplication.Source = ConsentSource{}
	_ activityapplication.Source = SubscriptionSource{}
	_ activityapplication.Source = DataControlSource{}
)

func NewRunSource(reader RunReader) RunSource             { return RunSource{reader: reader} }
func NewConsentSource(reader ConsentReader) ConsentSource { return ConsentSource{reader: reader} }
func NewSubscriptionSource(reader SubscriptionReader) SubscriptionSource {
	return SubscriptionSource{reader: reader}
}
func NewDataControlSource(reader DataControlReader) DataControlSource {
	return DataControlSource{reader: reader}
}

func (source RunSource) ListSkillActivities(
	ctx context.Context,
	accountID string,
	skillID string,
	limit int,
) ([]activitymodel.Item, error) {
	if source.reader == nil {
		return nil, activitymodel.ErrUnavailable
	}
	events, err := source.reader.ListSkillActivityEvents(ctx, accountID, skillID, limit)
	if err != nil {
		return nil, err
	}
	items := make([]activitymodel.Item, 0, len(events))
	for _, event := range events {
		semantics, semanticErr := activitymodel.ResolveSemantics(
			activitymodel.KindRun,
			event.State,
		)
		if semanticErr != nil {
			return nil, activitymodel.ErrUnavailable
		}
		failureCode := redactFailureCode(event.FailureCode, "assistant_run_failed")
		items = append(items, activitymodel.Item{
			ActivityID:      activitymodel.StableID(activitymodel.KindRun, event.RunID, event.Revision),
			AccountID:       event.UserID,
			SkillID:         event.SkillID,
			ActivityKind:    activitymodel.KindRun,
			Status:          event.State,
			DisplayKey:      semantics.DisplayKey,
			SourceObjectRef: "assistant.AssistantRun:" + event.RunID,
			SourceRevision:  event.Revision,
			RunID:           event.RunID,
			FailureCode:     failureCode,
			RecoveryAction:  semantics.RecoveryAction,
			OccurredAt:      event.OccurredAt,
		})
	}
	return items, nil
}

func (source ConsentSource) ListSkillActivities(
	ctx context.Context,
	accountID string,
	skillID string,
	limit int,
) ([]activitymodel.Item, error) {
	if source.reader == nil {
		return nil, activitymodel.ErrUnavailable
	}
	events, err := source.reader.ListSkillConsentEvents(ctx, accountID, skillID, limit)
	if err != nil {
		return nil, err
	}
	items := make([]activitymodel.Item, 0, len(events))
	for _, event := range events {
		var status string
		switch event.EventName {
		case consentmodel.EventGranted:
			status = "granted"
		case consentmodel.EventRevoked:
			status = "revoked"
		default:
			return nil, activitymodel.ErrUnavailable
		}
		semantics, semanticErr := activitymodel.ResolveSemantics(
			activitymodel.KindConsent,
			status,
		)
		if semanticErr != nil {
			return nil, activitymodel.ErrUnavailable
		}
		items = append(items, activitymodel.Item{
			ActivityID:      activitymodel.StableID(activitymodel.KindConsent, event.EventID, 0),
			AccountID:       event.AccountID,
			SkillID:         event.SkillID,
			ActivityKind:    activitymodel.KindConsent,
			Status:          status,
			DisplayKey:      semantics.DisplayKey,
			SourceObjectRef: "assistant.SkillConsent:" + event.AggregateID,
			SourceRevision:  0,
			ConsentID:       event.AggregateID,
			RecoveryAction:  semantics.RecoveryAction,
			OccurredAt:      event.OccurredAt,
		})
	}
	return items, nil
}

func (source SubscriptionSource) ListSkillActivities(
	ctx context.Context,
	accountID string,
	skillID string,
	limit int,
) ([]activitymodel.Item, error) {
	if source.reader == nil {
		return nil, activitymodel.ErrUnavailable
	}
	events, err := source.reader.ListSkillSubscriptionActivities(ctx, accountID, skillID, limit)
	if err != nil {
		return nil, err
	}
	items := make([]activitymodel.Item, 0, len(events))
	for _, event := range events {
		status := strings.TrimSpace(event.Status)
		semantics, semanticErr := activitymodel.ResolveSemantics(
			activitymodel.KindSubscription,
			status,
		)
		if semanticErr != nil {
			return nil, activitymodel.ErrUnavailable
		}
		items = append(items, activitymodel.Item{
			ActivityID:      activitymodel.StableID(activitymodel.KindSubscription, event.EventID, event.Version),
			AccountID:       event.OwnerID,
			SkillID:         event.SkillID,
			ActivityKind:    activitymodel.KindSubscription,
			Status:          status,
			DisplayKey:      semantics.DisplayKey,
			SourceObjectRef: "assistant.SkillSubscription:" + event.SubscriptionID,
			SourceRevision:  event.Version,
			SubscriptionID:  event.SubscriptionID,
			FailureCode:     redactFailureCode(event.FailureCode, "subscription_delivery_failed"),
			RecoveryAction:  semantics.RecoveryAction,
			OccurredAt:      event.OccurredAt,
		})
	}
	return items, nil
}

func (source DataControlSource) ListSkillActivities(
	ctx context.Context,
	accountID string,
	skillID string,
	limit int,
) ([]activitymodel.Item, error) {
	if source.reader == nil {
		return nil, activitymodel.ErrUnavailable
	}
	events, err := source.reader.ListSkillDataControlActivities(ctx, accountID, skillID, limit)
	if err != nil {
		return nil, err
	}
	items := make([]activitymodel.Item, 0, len(events))
	for _, event := range events {
		semantics, semanticErr := activitymodel.ResolveSemantics(
			activitymodel.KindDataControl,
			event.Status,
		)
		if semanticErr != nil {
			return nil, activitymodel.ErrUnavailable
		}
		items = append(items, activitymodel.Item{
			ActivityID:           activitymodel.StableID(activitymodel.KindDataControl, event.EventID, event.Revision),
			AccountID:            event.AccountID,
			SkillID:              event.SkillID,
			ActivityKind:         activitymodel.KindDataControl,
			Status:               event.Status,
			DisplayKey:           semantics.DisplayKey,
			SourceObjectRef:      "assistant.SkillDataControlRequest:" + event.RequestID,
			SourceRevision:       event.Revision,
			DataControlRequestID: event.RequestID,
			FailureCode:          redactFailureCode(event.FailureCode, "data_control_action_failed"),
			RecoveryAction:       semantics.RecoveryAction,
			OccurredAt:           event.OccurredAt,
		})
	}
	return items, nil
}

func redactFailureCode(value string, fallback string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	if safeFailureCode.MatchString(value) {
		return value
	}
	return fallback
}
