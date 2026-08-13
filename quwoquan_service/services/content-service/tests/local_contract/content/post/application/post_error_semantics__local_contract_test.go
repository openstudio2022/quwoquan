// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// Post 对象声明错误码的负例断言：真实驱动 PostService 拒绝路径到
// generated AppError 工厂的 emit 点，并以字面 wire code 锁定端云契约。
package post_test

import (
	"context"
	"errors"
	"testing"

	. "quwoquan_service/services/content-service/internal/content/post/application"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

func requirePostAppErrorCode(t *testing.T, err error, wantCode string) {
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

func TestUpdatePostSettingsByNonOwnerEmitsForbiddenEdit(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	published, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-forbidden-edit"),
		testPublicationCommand("err-sem-forbidden-edit", "draft-err-sem-forbidden"),
	)
	if err != nil {
		t.Fatalf("publish post before settings update: %v", err)
	}

	_, err = service.UpdatePostSettings(
		context.Background(),
		published.PostID,
		"persona-intruder",
		map[string]any{"visibility": "private"},
	)
	requirePostAppErrorCode(t, err, "CONTENT.USER.forbidden_edit")
}
