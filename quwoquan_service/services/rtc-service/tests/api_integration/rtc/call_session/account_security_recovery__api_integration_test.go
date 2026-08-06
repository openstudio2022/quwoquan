// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-004
// readiness_case: recover-rtc-account-closure-dead-letter-api
package api_integration

import (
	"bytes"
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	rtccache "quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/cache"
)

func TestRtcAccountClosureRecoveryRouteClearsRealRedisTerminalMarker(t *testing.T) {
	ctx := context.Background()
	const sourceStreamID = "1710000000000-4242"
	failures := rtccache.NewAccountSecurityEventFailureStore(
		redisRouter.Scene("general"),
	)
	t.Cleanup(func() {
		_ = failures.ClearAccountSecurityFailure(
			context.Background(),
			mq.UserAccountSecurityEventStream,
			sourceStreamID,
		)
	})
	if _, err := failures.RecordAccountSecurityFailure(
		ctx,
		mq.UserAccountSecurityEventStream,
		sourceStreamID,
		"event-recovery-api-001",
		"dependency",
		errors.New("media room revocation unavailable"),
	); err != nil {
		t.Fatalf("record real Redis failure state: %v", err)
	}
	if err := failures.MarkAccountSecurityDeadLettered(
		ctx,
		mq.UserAccountSecurityEventStream,
		sourceStreamID,
	); err != nil {
		t.Fatalf("mark real Redis terminal state: %v", err)
	}

	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"rtc-account-security-recovery-api",
		runtimemessaging.RedisMessageTransportAdapter,
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
	)
	if err != nil {
		t.Fatalf("construct real Redis message transport: %v", err)
	}
	consumer, err := mq.NewUserAccountSecurityConsumer(
		transport,
		apiTerminalCloser{},
		failures,
		"rtc-account-security-recovery-api",
		nil,
		mq.DefaultUserAccountSecurityConsumerConfig(),
	)
	if err != nil {
		t.Fatalf("construct production account security consumer: %v", err)
	}
	handler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/rtc/account-closure/dead-letters:recover",
			Module:   rterr.ModuleRTC,
			Releaser: consumer,
		},
	)
	if err != nil {
		t.Fatalf("construct production recovery route: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/rtc/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"1710000000000-4242"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "rtc-account-closure-recovery-api-001")
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("recovery status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	deadLettered, err := failures.IsAccountSecurityDeadLettered(
		ctx,
		mq.UserAccountSecurityEventStream,
		sourceStreamID,
	)
	if err != nil {
		t.Fatalf("read real Redis failure state: %v", err)
	}
	if deadLettered {
		t.Fatal("recovery route left the source PEL marker held")
	}
}

type apiTerminalCloser struct{}

func (apiTerminalCloser) ApplyAccountSecurityTerminalEvent(
	context.Context,
	application.AccountSecurityTerminalEvent,
) (application.AccountSecurityTerminalApplyResult, error) {
	return application.AccountSecurityTerminalApplyResult{}, nil
}
