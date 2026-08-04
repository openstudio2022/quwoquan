package control

import (
	"context"
	"errors"
	"fmt"

	activityports "quwoquan_service/services/assistant-service/internal/assistant/skill_activity_view/domain/ports"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_data_control_request/domain/model"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	subscriptionmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
)

const maxSubscriptionsPerControlRequest = 1000

type Executor struct {
	visibility    activityports.VisibilityStore
	consent       *consentapplication.CommandFacade
	subscriptions *subscriptionapplication.UseCases
	skillReader   subscriptionports.SkillScopedReader
}

func NewExecutor(
	visibility activityports.VisibilityStore,
	consent *consentapplication.CommandFacade,
	subscriptions *subscriptionapplication.UseCases,
	skillReader subscriptionports.SkillScopedReader,
) *Executor {
	return &Executor{
		visibility:    visibility,
		consent:       consent,
		subscriptions: subscriptions,
		skillReader:   skillReader,
	}
}

func (executor *Executor) ExecuteSkillDataControlAction(
	ctx context.Context,
	request model.Request,
	action string,
) error {
	switch action {
	case model.ActionHideActivityHistory:
		if executor.visibility == nil || request.ConfirmedAt == nil {
			return errors.New("skill activity visibility owner is unavailable")
		}
		return executor.visibility.HideBefore(
			ctx, request.AccountID, request.SkillID, request.ConfirmedAt.UTC(),
		)
	case model.ActionRevokeConsent:
		if executor.consent == nil {
			return errors.New("skill consent command owner is unavailable")
		}
		_, err := executor.consent.Revoke(
			ctx,
			request.RequestID+":"+model.ActionRevokeConsent,
			request.AccountID,
			request.SkillID,
		)
		return err
	case model.ActionArchiveSubscriptions:
		return executor.archiveSubscriptions(ctx, request)
	default:
		return model.ErrInvalidArgument
	}
}

func (executor *Executor) archiveSubscriptions(
	ctx context.Context,
	request model.Request,
) error {
	if executor.skillReader == nil || executor.subscriptions == nil {
		return errors.New("skill subscription command owner is unavailable")
	}
	if request.ConfirmedAt == nil {
		return model.ErrInvalidArgument
	}
	items, err := executor.skillReader.ListSkillSubscriptionsBySkill(
		ctx,
		request.AccountID,
		request.SkillID,
		request.ConfirmedAt.UTC(),
		maxSubscriptionsPerControlRequest+1,
	)
	if err != nil {
		return err
	}
	if len(items) > maxSubscriptionsPerControlRequest {
		return fmt.Errorf("skill subscription control set exceeds %d", maxSubscriptionsPerControlRequest)
	}
	for _, item := range items {
		if item.Status == subscriptionmodel.SkillSubscriptionStatusArchived {
			continue
		}
		_, err := executor.subscriptions.UpdateStatus(
			ctx,
			request.AccountID,
			item.SubscriptionID,
			subscriptionmodel.UpdateSkillSubscriptionStatusInput{
				Status: subscriptionmodel.SkillSubscriptionStatusArchived,
				ClientRequestID: request.RequestID + ":" +
					model.ActionArchiveSubscriptions + ":" + item.SubscriptionID,
			},
		)
		if err != nil {
			return err
		}
	}
	return nil
}
