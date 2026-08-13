// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// AppMessage 声明错误码的负例断言：以对象级 typed double 驱动读写失败、
// 幂等冲突与匿名越权路径，并经 cmd/api 同款 dead-letter 恢复路由驱动
// internal_error，以字面 wire code 锁定端云契约。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rterrors "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
	reliabletask "quwoquan_service/runtime/reliabletask"
)

type errSemAppMessageStore struct {
	findErr   error
	found     bool
	existing  notification.AppMessage
	createErr error
}

func (s errSemAppMessageStore) Create(
	_ context.Context, message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	if s.createErr != nil {
		return notification.AppMessage{}, false, s.createErr
	}
	return message, true, nil
}

func (s errSemAppMessageStore) FindByIdempotencyKey(
	context.Context, string,
) (notification.AppMessage, bool, error) {
	return s.existing, s.found, s.findErr
}

func (s errSemAppMessageStore) Acknowledge(
	context.Context, string, string, time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, nil
}

func (s errSemAppMessageStore) MarkRead(
	context.Context, string, string, time.Time,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, nil
}

type errSemAppMessageTx struct{}

func (errSemAppMessageTx) RunInTransaction(
	ctx context.Context, fn func(context.Context) error,
) error {
	return fn(ctx)
}

type errSemDeliveryOutbox struct{}

func (errSemDeliveryOutbox) CreateNotification(
	_ context.Context, record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	return record, nil
}

type errSemInboxReader struct{}

func (errSemInboxReader) ListInbox(
	context.Context, application.AppMessageInboxQuery,
) (notification.AppMessageInboxSlice, error) {
	return notification.AppMessageInboxSlice{}, nil
}

type errSemDetailReader struct{}

func (errSemDetailReader) Get(
	context.Context, string, string,
) (notification.AppMessage, error) {
	return notification.AppMessage{}, nil
}

type errSemUnreadCountReader struct{}

func (errSemUnreadCountReader) CountUnread(context.Context, string) (int64, error) {
	return 0, nil
}

func errSemCreateCommand() application.CreateAppMessageCommand {
	return application.CreateAppMessageCommand{
		IdempotencyKey: "app-message-errsem-key",
		UserID:         "user-errsem",
		Source:         "system",
		SourceID:       "source-errsem",
		Title:          "系统通知",
		Summary:        "错误语义负例",
	}
}

func errSemCreateAppMessage(t *testing.T, store errSemAppMessageStore) error {
	t.Helper()
	facade, err := application.NewAppMessageCommandFacade(
		store, errSemAppMessageTx{}, errSemDeliveryOutbox{},
	)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}
	_, err = facade.Create(context.Background(), errSemCreateCommand())
	return err
}

func requireAppMessageErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rterrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func TestCreateAppMessageIdempotencyReadFailureEmitsStorageReadFailed(t *testing.T) {
	err := errSemCreateAppMessage(t, errSemAppMessageStore{
		findErr: errors.New("mongo find timed out"),
	})
	requireAppMessageErrorCode(t, err, "NOTIFICATION.SYSTEM.storage_read_failed")
}

func TestCreateAppMessagePayloadMismatchEmitsIdempotencyConflict(t *testing.T) {
	err := errSemCreateAppMessage(t, errSemAppMessageStore{
		found:    true,
		existing: notification.AppMessage{MessageID: "msg-other", UserID: "someone-else"},
	})
	requireAppMessageErrorCode(t, err, "NOTIFICATION.USER.idempotency_conflict")
}

func TestCreateAppMessageInsertFailureEmitsStorageWriteFailed(t *testing.T) {
	err := errSemCreateAppMessage(t, errSemAppMessageStore{
		createErr: errors.New("mongo insert failed"),
	})
	requireAppMessageErrorCode(t, err, "NOTIFICATION.SYSTEM.storage_write_failed")
}

func TestListInboxWithoutAccountEmitsUnauthorized(t *testing.T) {
	queries, err := application.NewAppMessageQueryFacade(
		errSemInboxReader{}, errSemDetailReader{}, errSemUnreadCountReader{},
	)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}

	_, err = queries.ListInbox(context.Background(), application.AppMessageInboxQuery{})
	requireAppMessageErrorCode(t, err, "NOTIFICATION.USER.unauthorized")
}

type errSemNotificationReleaser struct{}

func (errSemNotificationReleaser) RecoverDeadLetter(context.Context, string) error {
	return errors.New("redis XACK failed")
}

func TestAccountClosureDeadLetterReleaseFailureEmitsNotificationInternalError(t *testing.T) {
	handler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/notification/account-closure/dead-letters:recover",
			Module:   rterrors.ModuleNotification,
			Releaser: errSemNotificationReleaser{},
		},
	)
	if err != nil {
		t.Fatalf("compose dead-letter recovery route: %v", err)
	}

	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/notification/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"1723500000000-0"}`),
	)
	request.Header.Set("Idempotency-Key", "notification-dead-letter-errsem")
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)

	if response.Code != http.StatusInternalServerError {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v body=%s", err, response.Body.String())
	}
	if envelope.Code != "NOTIFICATION.SYSTEM.internal_error" {
		t.Fatalf("expected code NOTIFICATION.SYSTEM.internal_error, got %s", envelope.Code)
	}
}
