// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// PostModerationCase 声明错误码的负例断言：真实驱动 ModerationService
// 拒绝路径到 generated AppError 工厂的 emit 点，并以字面 wire code 锁定
// 端云契约。
package moderation_test

import (
	"context"
	"errors"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
)

func requireModerationAppErrorCode(t *testing.T, err error, wantCode string) {
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

func TestReviewUnknownCaseEmitsModerationCaseNotFound(t *testing.T) {
	t.Parallel()

	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(mediacontract.NewModerationStore()),
	)
	_, err := service.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "err-sem-review-unknown"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID:     "post-err-sem",
			CaseID:     "pmc-absent",
			ReviewerID: "reviewer-err-sem",
		},
	)
	requireModerationAppErrorCode(t, err, "CONTENT.USER.moderation_case_not_found")
}
