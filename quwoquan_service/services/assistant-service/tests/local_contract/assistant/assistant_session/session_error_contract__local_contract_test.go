// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// 错误契约语义双向锁：AssistantSession 的 session_not_found 与
// session_storage_unavailable 由真实触发条件触发，并断言 canonical code 与
// http_status。
package local_contract

import (
	"context"
	"errors"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	sessionmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/model"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
)

// emptySessionStore 是对象级 typed double：聚合读取永远 miss。
type emptySessionStore struct{}

func (emptySessionStore) InsertSession(
	_ context.Context,
	session sessionmodel.AssistantSession,
) (sessionmodel.AssistantSession, bool, error) {
	return session, false, nil
}

func (emptySessionStore) GetSession(
	context.Context,
	string,
) (sessionmodel.AssistantSession, bool, error) {
	return sessionmodel.AssistantSession{}, false, nil
}

func (emptySessionStore) OwnedSessionExists(
	context.Context,
	string,
	string,
) (bool, error) {
	return false, nil
}

func (emptySessionStore) ListSessions(
	context.Context,
	string,
	int,
	string,
) ([]sessionmodel.AssistantSession, string, error) {
	return nil, "", nil
}

func (emptySessionStore) CommitSessionSummary(
	context.Context,
	sessionports.SessionSummaryCommit,
) (sessionports.SessionSummaryCommitResult, error) {
	return sessionports.SessionSummaryCommitResult{}, nil
}

func assertSessionError(t *testing.T, err error, code string, status int) {
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

func TestGetSessionEmitsCanonicalNotFoundAndStorageUnavailable(t *testing.T) {
	t.Parallel()

	withStore := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionStore(emptySessionStore{}),
	)
	_, err := withStore.GetSession(
		t.Context(),
		"account-session-error",
		"asn_missing",
	)
	assertSessionError(t, err, "ASSISTANT.USER.session_not_found", 404)

	withoutStore := orchestration.NewAssistantService(nil, nil)
	_, err = withoutStore.GetSession(
		t.Context(),
		"account-session-error",
		"asn_any",
	)
	assertSessionError(
		t,
		err,
		"ASSISTANT.SYSTEM.session_storage_unavailable",
		503,
	)
}
