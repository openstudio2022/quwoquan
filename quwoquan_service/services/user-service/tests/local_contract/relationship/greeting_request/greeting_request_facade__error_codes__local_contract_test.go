package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	greetingapp "quwoquan_service/services/user-service/internal/relationship/greeting_request/application"
)

func assertGreetingErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

func newGreetingErrorCodeService(store *facadeGreetingStore) *greetingapp.GreetingService {
	return greetingapp.NewGreetingService(
		store,
		store,
		failOpenRelationships{},
		failOpenConversationGateway{},
		failOpenEventPublisher{},
		failOpenGreetingStream{},
		staticGreetingRecipientAccounts{"target": "target-account"},
		allowGreetingPolicy{},
	)
}

// quotaExhaustedGreetingCommands 复用 facade store,仅把 24h 发送计数固定在配额上限。
type quotaExhaustedGreetingCommands struct {
	*facadeGreetingStore
}

func (quotaExhaustedGreetingCommands) CountRecentByRequester(
	context.Context,
	string,
	time.Duration,
) (int64, error) {
	return 20, nil
}

func TestGreetingSendSurfacesRateLimitedAtDailyQuota(t *testing.T) {
	t.Parallel()
	store := newFacadeGreetingStore()
	service := greetingapp.NewGreetingService(
		store,
		quotaExhaustedGreetingCommands{store},
		failOpenRelationships{},
		failOpenConversationGateway{},
		failOpenEventPublisher{},
		failOpenGreetingStream{},
		staticGreetingRecipientAccounts{"target": "target-account"},
		allowGreetingPolicy{},
	)

	_, err := service.Send(context.Background(), greetingapp.SendGreetingRequest{
		RequesterPersonaID: "requester",
		TargetPersonaID:    "target",
		RequestMessage:     "你好",
		Source:             "profile",
		IdempotencyKey:     "send-over-quota",
	})
	assertGreetingErrorCode(t, err, "USER.GREETING.rate_limited")
}

func TestGreetingSendSurfacesDuplicatePending(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := newGreetingErrorCodeService(newFacadeGreetingStore())

	if _, err := service.Send(ctx, greetingapp.SendGreetingRequest{
		RequesterPersonaID: "requester",
		TargetPersonaID:    "target",
		RequestMessage:     "你好",
		Source:             "profile",
		IdempotencyKey:     "send-first",
	}); err != nil {
		t.Fatalf("first SendGreetingRequest: %v", err)
	}

	_, err := service.Send(ctx, greetingapp.SendGreetingRequest{
		RequesterPersonaID: "requester",
		TargetPersonaID:    "target",
		RequestMessage:     "再次打招呼",
		Source:             "profile",
		IdempotencyKey:     "send-second",
	})
	assertGreetingErrorCode(t, err, "USER.GREETING.duplicate_pending")
}

func TestGreetingReplySurfacesNotFoundForUnknownOrForeignRequest(t *testing.T) {
	t.Parallel()
	service := newGreetingErrorCodeService(newFacadeGreetingStore())

	_, err := service.Reply(
		context.Background(),
		"target",
		"missing-greeting-id",
		"reply-missing",
	)
	assertGreetingErrorCode(t, err, "USER.GREETING.not_found")
}

func TestGreetingReplySurfacesInvalidStatusTransitionAfterIgnore(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	service := newGreetingErrorCodeService(newFacadeGreetingStore())

	greeting, err := service.Send(ctx, greetingapp.SendGreetingRequest{
		RequesterPersonaID: "requester",
		TargetPersonaID:    "target",
		RequestMessage:     "你好",
		Source:             "profile",
		IdempotencyKey:     "send-for-transition",
	})
	if err != nil {
		t.Fatalf("SendGreetingRequest: %v", err)
	}
	if _, err := service.Ignore(ctx, "target", greeting.ID, "ignore-first"); err != nil {
		t.Fatalf("IgnoreGreetingRequest: %v", err)
	}

	_, err = service.Reply(ctx, "target", greeting.ID, "reply-after-ignore")
	assertGreetingErrorCode(t, err, "USER.GREETING.invalid_status_transition")
}
