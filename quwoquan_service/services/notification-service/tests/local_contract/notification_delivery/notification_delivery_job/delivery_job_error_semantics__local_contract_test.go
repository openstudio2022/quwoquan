// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// NotificationDeliveryJob 声明错误码的负例断言：以 typed reader double 驱动
// 存储读取失败，经真实 HTTP handler 驱动匿名 ACK 越权，以字面 wire code
// 锁定端云契约。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rterrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/adapters/inbound/http"
	application "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/domain"
)

type errSemFailingMetricsReader struct{}

func (errSemFailingMetricsReader) ReadDeliveryJobMetrics(
	context.Context,
) (notification.NotificationDeliveryJobMetricsSnapshot, error) {
	return notification.NotificationDeliveryJobMetricsSnapshot{},
		errors.New("mongo aggregate timed out")
}

type errSemEmptyDeadLetterReader struct{}

func (errSemEmptyDeadLetterReader) ListDeadDeliveryJobs(
	context.Context, []string, int,
) ([]reliabletask.DeadNotificationRecord, error) {
	return nil, nil
}

func TestDeliveryJobMetricsReadFailureEmitsDeliveryJobStorageReadFailed(t *testing.T) {
	queries, err := application.NewNotificationDeliveryJobQueryFacade(
		errSemFailingMetricsReader{}, errSemEmptyDeadLetterReader{},
	)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}

	_, err = queries.GetMetrics(context.Background())
	if err == nil {
		t.Fatal("expected AppError, got nil")
	}
	var appErr *rterrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError, got %v", err)
	}
	if appErr.Code.String() != "NOTIFICATION.SYSTEM.delivery_job_storage_read_failed" {
		t.Fatalf(
			"expected code NOTIFICATION.SYSTEM.delivery_job_storage_read_failed, got %s",
			appErr.Code.String(),
		)
	}
}

func TestIncomingCallAckWithoutPrincipalEmitsDeliveryJobUnauthorized(t *testing.T) {
	stub := &deliveryOpsStoreStub{}
	commands, err := application.NewNotificationDeliveryJobCommandFacade(stub)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}
	queries, err := application.NewNotificationDeliveryJobQueryFacade(stub, stub)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}
	handler, err := httpadapter.NewHandler(commands, queries)
	if err != nil {
		t.Fatalf("construct handler: %v", err)
	}
	handler = handler.WithIncomingCallCoordinator(&application.IncomingCallDeliveryCoordinator{})
	mux := http.NewServeMux()
	handler.RegisterRoutes(mux)

	request := httptest.NewRequest(
		http.MethodPost,
		"/notifications/incoming-calls/presentation:ack",
		bytes.NewBufferString(`{"deliveryKey":"delivery-errsem"}`),
	)
	response := httptest.NewRecorder()
	mux.ServeHTTP(response, request)

	if response.Code != http.StatusUnauthorized {
		t.Fatalf("status=%d body=%s", response.Code, response.Body.String())
	}
	var envelope struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode error envelope: %v body=%s", err, response.Body.String())
	}
	if envelope.Code != "NOTIFICATION.USER.delivery_job_unauthorized" {
		t.Fatalf(
			"expected code NOTIFICATION.USER.delivery_job_unauthorized, got %s",
			envelope.Code,
		)
	}
}
