// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// MediaUploadSession 声明错误码的负例断言：每个用例真实驱动 application
// 拒绝路径到 generated AppError 工厂的 emit 点，并以字面 wire code 锁定
// 端云契约。
package media_upload_session_test

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
)

func requireUploadSessionAppErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func TestCompleteUnknownUploadSessionEmitsMediaNotFound(t *testing.T) {
	t.Parallel()

	service := sessionapp.NewUseCases(newMemoryStore(), &memoryObjectStore{})
	_, err := service.Complete(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-complete-unknown"),
		sessionapp.CompleteCommand{
			SessionID: "session-absent", OwnerID: "persona-1", AccessPolicy: "owner_only",
		},
	)
	requireUploadSessionAppErrorCode(t, err, "CONTENT.USER.media_not_found")
}

func TestCompleteExpiredUploadSessionEmitsMediaUploadSessionExpired(t *testing.T) {
	t.Parallel()

	current := time.Date(2026, 8, 1, 12, 0, 0, 0, time.UTC)
	store := newMemoryStore()
	sequence := 0
	service := sessionapp.NewUseCases(
		store,
		&memoryObjectStore{now: current},
		sessionapp.WithClock(func() time.Time { return current }),
		sessionapp.WithIdentifierGenerator(func(prefix string) (string, error) {
			sequence++
			return fmt.Sprintf("%s_err_sem_%d", prefix, sequence), nil
		}),
	)
	initialized, err := service.Init(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-expired-init"),
		sessionapp.InitCommand{
			OwnerID: "persona-expired", MediaType: "image", MimeType: "image/jpeg",
			FileSize: 128, ExpectedSHA256: testSHA256,
		},
	)
	if err != nil {
		t.Fatalf("init upload before expiry: %v", err)
	}

	current = initialized.ExpiresAt
	_, err = service.Complete(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-expired-complete"),
		sessionapp.CompleteCommand{
			SessionID: initialized.SessionID, OwnerID: "persona-expired",
			AccessPolicy: "owner_only",
		},
	)
	requireUploadSessionAppErrorCode(t, err, "CONTENT.USER.media_upload_session_expired")
}
