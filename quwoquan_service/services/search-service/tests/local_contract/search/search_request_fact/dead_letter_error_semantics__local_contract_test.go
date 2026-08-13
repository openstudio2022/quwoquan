// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// SearchRequestFact 声明错误码的负例断言：经 cmd/api 同款 dead-letter 恢复
// 路由组合驱动 PEL 释放失败路径，以字面 wire code 锁定端云契约。
package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	runtimemessaging "quwoquan_service/runtime/messaging"
)

type errSemFailingReleaser struct{}

func (errSemFailingReleaser) RecoverDeadLetter(context.Context, string) error {
	return errors.New("redis XACK failed")
}

func TestAccountClosureDeadLetterReleaseFailureEmitsInternalError(t *testing.T) {
	handler, err := runtimemessaging.WithDeadLetterRecoveryRoute(
		http.NotFoundHandler(),
		runtimemessaging.DeadLetterRecoveryRouteConfig{
			Path:     "/internal/search/account-closure/dead-letters:recover",
			Module:   rterr.ModuleSearch,
			Releaser: errSemFailingReleaser{},
		},
	)
	if err != nil {
		t.Fatalf("compose dead-letter recovery route: %v", err)
	}

	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/search/account-closure/dead-letters:recover",
		bytes.NewBufferString(`{"sourceStreamId":"1723500000000-0"}`),
	)
	request.Header.Set("Idempotency-Key", "dead-letter-errsem-key")
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
	if envelope.Code != "SEARCH.SYSTEM.internal_error" {
		t.Fatalf("expected code SEARCH.SYSTEM.internal_error, got %s", envelope.Code)
	}
}
