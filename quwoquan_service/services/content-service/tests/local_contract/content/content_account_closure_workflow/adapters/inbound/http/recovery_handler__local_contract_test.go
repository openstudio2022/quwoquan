// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003
// readiness_case: recover-content-account-closure-dead-letter-local
package content_account_closure_workflow_test

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	closurehttp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/adapters/inbound/http"
	closureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
)

type recordingRecoveryPort struct {
	recovered []string
	err       error
}

func (port *recordingRecoveryPort) RecoverDeadLetter(
	_ context.Context,
	sourceStreamID string,
) error {
	port.recovered = append(port.recovered, sourceStreamID)
	return port.err
}

func TestRecoveryHandlerExecutesObjectCommandAndRuntimeErrorBoundary(t *testing.T) {
	port := &recordingRecoveryPort{}
	commands, err := closureapp.NewContentAccountClosureRecoveryCommandFacet(port)
	if err != nil {
		t.Fatalf("new recovery commands: %v", err)
	}
	handler, err := closurehttp.NewHandler(commands)
	if err != nil {
		t.Fatalf("new recovery handler: %v", err)
	}
	mounted, err := handler.Mount(http.NotFoundHandler())
	if err != nil {
		t.Fatalf("mount recovery handler: %v", err)
	}

	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/account-closure/dead-letters:recover",
		strings.NewReader(`{"sourceStreamId":"1700000000000-0"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "recover-once")
	recorder := httptest.NewRecorder()
	mounted.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusAccepted {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	if len(port.recovered) != 1 || port.recovered[0] != "1700000000000-0" {
		t.Fatalf("recovery calls=%v", port.recovered)
	}
	var response map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode response: %v", err)
	}
	if response["sourceStreamId"] != "1700000000000-0" || response["recoveryAccepted"] != true {
		t.Fatalf("response=%v", response)
	}

	port.err = errors.New("storage unavailable")
	failing := httptest.NewRecorder()
	mounted.ServeHTTP(failing, requestWithRecoveryBody(t, "1700000000001-0", "recover-twice"))
	if failing.Code != http.StatusInternalServerError ||
		!strings.Contains(failing.Body.String(), "CONTENT.SYSTEM.internal_error") {
		t.Fatalf("runtime error status=%d body=%s", failing.Code, failing.Body.String())
	}
}

func TestRecoveryHandlerRejectsInvalidWireBeforeApplication(t *testing.T) {
	port := &recordingRecoveryPort{}
	commands, _ := closureapp.NewContentAccountClosureRecoveryCommandFacet(port)
	handler, _ := closurehttp.NewHandler(commands)
	mounted, _ := handler.Mount(http.NotFoundHandler())

	for name, request := range map[string]*http.Request{
		"missing idempotency": httptest.NewRequest(
			http.MethodPost,
			"/internal/content/account-closure/dead-letters:recover",
			strings.NewReader(`{"sourceStreamId":"1700000000000-0"}`),
		),
		"invalid stream": requestWithRecoveryBody(t, "not-a-stream-id", "recover-invalid"),
		"unknown field": httptest.NewRequest(
			http.MethodPost,
			"/internal/content/account-closure/dead-letters:recover",
			strings.NewReader(`{"sourceStreamId":"1700000000000-0","payload":"forbidden"}`),
		),
	} {
		t.Run(name, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			mounted.ServeHTTP(recorder, request)
			if recorder.Code != http.StatusBadRequest ||
				!strings.Contains(recorder.Body.String(), "CONTENT.USER.invalid_argument") {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
		})
	}
	if len(port.recovered) != 0 {
		t.Fatalf("invalid wire reached application port: %v", port.recovered)
	}
}

func requestWithRecoveryBody(t *testing.T, sourceStreamID, idempotencyKey string) *http.Request {
	t.Helper()
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/account-closure/dead-letters:recover",
		strings.NewReader(`{"sourceStreamId":"`+sourceStreamID+`"}`),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", idempotencyKey)
	return request
}
