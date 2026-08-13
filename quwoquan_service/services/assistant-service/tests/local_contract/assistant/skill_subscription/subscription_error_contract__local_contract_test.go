// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-002
// 错误契约语义双向锁：SkillSubscription errors.yaml 声明的错误码由真实触发条件
// 触发，并断言 canonical code 与 http_status。
package skill_subscription_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
	subscriptionpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/infrastructure/persistence"
)

type subscriptionMembershipStub struct {
	member bool
	err    error
}

func (stub subscriptionMembershipStub) ResolveAssistantDeliveryMembership(
	context.Context,
	string,
	string,
	string,
) (bool, error) {
	return stub.member, stub.err
}

func assertSubscriptionError(t *testing.T, err error, code string, status int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("error=%T %v, want *rterr.AppError", err, err)
	}
	if appErr.Code.String() != code || appErr.HTTPStatus != status {
		t.Fatalf(
			"error=%s/%d, want %s/%d",
			appErr.Code.String(),
			appErr.HTTPStatus,
			code,
			status,
		)
	}
}

func validCreateSubscriptionInput(clientRequestID string) skillmodel.CreateSkillSubscriptionInput {
	return skillmodel.CreateSkillSubscriptionInput{
		SkillID:  "news_briefing",
		DomainID: "news",
		Trigger: skillmodel.SkillSubscriptionTrigger{
			Type:     "cron",
			Cron:     "30 8 * * *",
			Timezone: "Asia/Shanghai",
		},
		Destination: skillmodel.SkillSubscriptionDestination{
			DestinationType: skillmodel.SkillSubscriptionDestinationUser,
		},
		ClientRequestID: clientRequestID,
	}
}

func chatDestinationInput(clientRequestID string) skillmodel.CreateSkillSubscriptionInput {
	input := validCreateSubscriptionInput(clientRequestID)
	input.CreatedByPersonaID = "persona-subscription-error"
	input.Destination = skillmodel.SkillSubscriptionDestination{
		DestinationType: skillmodel.SkillSubscriptionDestinationChatConversation,
		DestinationID:   "conversation-1",
	}
	return input
}

func TestSkillSubscriptionUseCasesEmitCanonicalErrorContract(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 8, 13, 9, 0, 0, 0, time.UTC)
	newUseCases := func(
		memberships subscriptionapplication.DestinationMembershipReader,
		ticker subscriptionapplication.CronTicker,
	) (*subscriptionapplication.UseCases, *subscriptionpersistence.MemoryStore) {
		store := subscriptionpersistence.NewMemoryStore()
		return subscriptionapplication.NewUseCases(
			store,
			memberships,
			ticker,
			func() time.Time { return now },
		), store
	}

	t.Run("blank skill id is subscription_invalid_argument", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(nil, nil)
		input := validCreateSubscriptionInput("create-blank-skill")
		input.SkillID = " "
		_, err := useCases.Create(t.Context(), "account-subscription-error", input)
		assertSubscriptionError(
			t, err, "ASSISTANT.USER.subscription_invalid_argument", 400,
		)
	})

	t.Run("archived subscription cannot transition is subscription_invalid_transition", func(t *testing.T) {
		t.Parallel()
		useCases, store := newUseCases(nil, nil)
		store.SeedSkillSubscription(skillmodel.SkillSubscription{
			SubscriptionID: "subscription-archived",
			Version:        1,
			Owner: skillmodel.SkillSubscriptionOwner{
				OwnerType: "user",
				OwnerID:   "account-subscription-error",
			},
			CreatedByUserID: "account-subscription-error",
			SkillID:         "news_briefing",
			DomainID:        "news",
			Status:          skillmodel.SkillSubscriptionStatusArchived,
			CreatedAt:       now,
			UpdatedAt:       now,
		})
		_, err := useCases.UpdateStatus(
			t.Context(),
			"account-subscription-error",
			"subscription-archived",
			skillmodel.UpdateSkillSubscriptionStatusInput{
				Status:          skillmodel.SkillSubscriptionStatusActive,
				ClientRequestID: "reactivate-archived",
			},
		)
		assertSubscriptionError(
			t, err, "ASSISTANT.USER.subscription_invalid_transition", 409,
		)
	})

	t.Run("missing subscription is subscription_not_found", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(nil, nil)
		_, err := useCases.Get(
			t.Context(),
			"account-subscription-error",
			"subscription-missing",
		)
		assertSubscriptionError(
			t, err, "ASSISTANT.USER.subscription_not_found", 404,
		)
	})

	t.Run("reused command with different payload is subscription_idempotency_conflict", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(nil, nil)
		if _, err := useCases.Create(
			t.Context(),
			"account-subscription-error",
			validCreateSubscriptionInput("create-reused"),
		); err != nil {
			t.Fatalf("seed create: %v", err)
		}
		drifted := validCreateSubscriptionInput("create-reused")
		drifted.TagRefs = []string{"different-payload"}
		_, err := useCases.Create(t.Context(), "account-subscription-error", drifted)
		assertSubscriptionError(
			t, err, "ASSISTANT.USER.subscription_idempotency_conflict", 409,
		)
	})

	t.Run("foreign chat destination is subscription_destination_forbidden", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(subscriptionMembershipStub{member: false}, nil)
		_, err := useCases.Create(
			t.Context(),
			"account-subscription-error",
			chatDestinationInput("create-forbidden-destination"),
		)
		assertSubscriptionError(
			t, err, "ASSISTANT.USER.subscription_destination_forbidden", 403,
		)
	})

	t.Run("missing membership reader is subscription_destination_validation_unavailable", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(nil, nil)
		_, err := useCases.Create(
			t.Context(),
			"account-subscription-error",
			chatDestinationInput("create-validation-unavailable"),
		)
		assertSubscriptionError(
			t,
			err,
			"ASSISTANT.SYSTEM.subscription_destination_validation_unavailable",
			503,
		)
	})

	t.Run("missing scheduler is subscription_delivery_failed", func(t *testing.T) {
		t.Parallel()
		useCases, _ := newUseCases(nil, nil)
		_, err := useCases.Tick(
			t.Context(),
			skillmodel.SkillSubscriptionCronTickInput{Now: now.Format(time.RFC3339)},
		)
		assertSubscriptionError(
			t, err, "ASSISTANT.SYSTEM.subscription_delivery_failed", 503,
		)
	})
}

func TestSubscriptionCronWithoutStoreIsSubscriptionStorageUnavailable(t *testing.T) {
	t.Parallel()
	service := orchestration.NewAssistantService(nil, nil)
	_, err := service.TickSkillSubscriptionCron(
		t.Context(),
		skillmodel.SkillSubscriptionCronTickInput{Now: "2026-08-13T09:00:00Z"},
	)
	assertSubscriptionError(
		t, err, "ASSISTANT.SYSTEM.subscription_storage_unavailable", 503,
	)
}
