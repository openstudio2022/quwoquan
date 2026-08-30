// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// PostModerationCase 的幂等回读与入参守卫路径。这些分支此前没有任何用例
// 稳定命中，覆盖率因此随抽样漂移；本文件用确定性输入把它们钉死：同 revision
// 的重复 Open 必须幂等回读既有 case，缺 idempotencyKey、postId 不匹配、
// 目标缺席、换人复审等守卫必须返回既定 AppError。
package moderation_test

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	mediacontract "quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport/media_contract"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationmodel "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/model"
)

const moderationGuardDigest = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

// 不注入 identifier generator，让服务使用真实的随机 case id 生成器。
func newGuardModerationService(
	store *mediacontract.ModerationStore,
) *moderationapp.ModerationService {
	return moderationapp.NewModerationService(moderationapp.BindDataPorts(store))
}

func TestRepeatedOpenOfSameRevisionIsIdempotent(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())
	command := moderationapp.OpenPostModerationCaseCommand{
		PostID:        "post-open-same-revision",
		PostVersion:   3,
		ContentDigest: moderationGuardDigest,
	}

	first, err := service.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-open-first"),
		command,
	)
	if err != nil || first.CaseID == "" {
		t.Fatalf("first open: result=%+v err=%v", first, err)
	}
	if !strings.HasPrefix(first.CaseID, "pmc_") {
		t.Fatalf("case id must come from the real identifier generator, got %q", first.CaseID)
	}

	// 另一路请求携带不同 idempotencyKey，因此绕开回执重放，只能靠
	// postId+postVersion+contentDigest 的 revision 唯一性判定。
	second, err := service.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-open-second"),
		command,
	)
	if err != nil {
		t.Fatalf("repeated open must read back the existing case, got err=%v", err)
	}
	if second.CaseID != first.CaseID {
		t.Fatalf("expected read-back of %s, got %s", first.CaseID, second.CaseID)
	}
	if !second.Replayed {
		t.Fatal("read-back result must be marked replayed")
	}
	if second.Status != moderationmodel.StatusPending {
		t.Fatalf("expected pending status on read-back, got %s", second.Status)
	}
}

func TestModerationCommandsRequireIdempotencyKey(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())
	const wantCode = "CONTENT.USER.invalid_argument"

	_, err := service.OpenPostModerationCase(
		context.Background(),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        "post-no-key",
			PostVersion:   1,
			ContentDigest: moderationGuardDigest,
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)

	_, err = service.ReviewPostModerationCase(
		context.Background(),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: "post-no-key", CaseID: "pmc-no-key", ReviewerID: "reviewer-no-key",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)

	_, err = service.DecidePostModerationCase(
		context.Background(),
		moderationapp.DecidePostModerationCaseCommand{
			PostID: "post-no-key", CaseID: "pmc-no-key", ReviewerID: "reviewer-no-key",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "no key",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)

	_, err = service.SupersedePostModerationCase(
		context.Background(),
		moderationapp.SupersedePostModerationCaseCommand{
			PostID: "post-no-key", CaseID: "pmc-no-key",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)
}

func TestGetCurrentPostModerationCaseGuardsPostID(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())

	_, err := service.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: "   "},
	)
	requireModerationAppErrorCode(t, err, "CONTENT.USER.invalid_argument")

	_, err = service.GetCurrentPostModerationCase(
		context.Background(),
		moderationapp.GetCurrentPostModerationCaseQuery{PostID: "post-never-moderated"},
	)
	requireModerationAppErrorCode(t, err, "CONTENT.USER.moderation_case_not_found")
}

func TestModerationCommandsRejectMismatchedPostID(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())
	opened, err := service.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-mismatch-open"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID:        "post-owns-case",
			PostVersion:   2,
			ContentDigest: moderationGuardDigest,
		},
	)
	if err != nil {
		t.Fatalf("open moderation case: %v", err)
	}

	const wantCode = "CONTENT.USER.invalid_argument"

	_, err = service.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-mismatch-review"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: "post-does-not-own-case", CaseID: opened.CaseID,
			ReviewerID: "reviewer-mismatch",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)

	_, err = service.SupersedePostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-mismatch-supersede"),
		moderationapp.SupersedePostModerationCaseCommand{
			PostID: "post-does-not-own-case", CaseID: opened.CaseID,
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)
}

func TestDecideAndSupersedeRejectAbsentCase(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())
	const wantCode = "CONTENT.USER.moderation_case_not_found"

	_, err := service.DecidePostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-decide-absent"),
		moderationapp.DecidePostModerationCaseCommand{
			PostID: "post-absent", CaseID: "pmc-absent", ReviewerID: "reviewer-absent",
			Decision: moderationmodel.DecisionApprove, DecisionReason: "case is gone",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)

	_, err = service.SupersedePostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-supersede-absent"),
		moderationapp.SupersedePostModerationCaseCommand{
			PostID: "post-absent", CaseID: "pmc-absent",
		},
	)
	requireModerationAppErrorCode(t, err, wantCode)
}

func TestReviewByAnotherReviewerIsForbiddenAfterReview(t *testing.T) {
	t.Parallel()

	service := newGuardModerationService(mediacontract.NewModerationStore())
	const postID = "post-two-reviewers"
	opened, err := service.OpenPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-forbidden-open"),
		moderationapp.OpenPostModerationCaseCommand{
			PostID: postID, PostVersion: 5, ContentDigest: moderationGuardDigest,
		},
	)
	if err != nil {
		t.Fatalf("open moderation case: %v", err)
	}

	if _, err = service.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-forbidden-review-one"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID, ReviewerID: "reviewer-first",
		},
	); err != nil {
		t.Fatalf("first review: %v", err)
	}

	// 同一 reviewer 再次进入是幂等回读，不同 reviewer 必须被拒。
	replayed, err := service.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-forbidden-review-again"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID, ReviewerID: "reviewer-first",
		},
	)
	if err != nil || !replayed.Replayed {
		t.Fatalf("same reviewer must read back the reviewed case: result=%+v err=%v", replayed, err)
	}

	_, err = service.ReviewPostModerationCase(
		commandmeta.WithIdempotencyKey(context.Background(), "guard-forbidden-review-two"),
		moderationapp.ReviewPostModerationCaseCommand{
			PostID: postID, CaseID: opened.CaseID, ReviewerID: "reviewer-second",
		},
	)
	requireModerationAppErrorCode(t, err, "CONTENT.USER.unauthorized")
}
