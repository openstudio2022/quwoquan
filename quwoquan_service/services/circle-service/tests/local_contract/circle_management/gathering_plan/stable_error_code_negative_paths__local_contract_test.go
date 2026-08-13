// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-plan-collaboration/spec.md#gwt-002
//
// 为 gathering_plan errors.yaml 声明的每个稳定错误码补真实断言：
// 每条 case 先经真实 application facade / HTTP adapter 触发对应 domain
// sentinel（权限、协作关闭、版本/基线/提案冲突、幂等冲突、存储失败注入），
// 再把该 sentinel 与 generated 稳定码（cmd/api mapGatheringPlanError 的映射
// 目标，源自 errors.yaml codegen）锚定在同一 case 中，防止声明与行为漂移。
package gathering_plan_test

import (
	"context"
	"errors"
	stdhttp "net/http"
	"net/http/httptest"
	"strings"
	"testing"

	planerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering_plan"
	planhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/ports"
)

var errPlanStorageDown = errors.New("gathering plan storage down")

func TestGatheringPlanNegativePathsEmitDeclaredStableCodes(t *testing.T) {
	tests := []struct {
		name      string
		domainErr error
		stableErr error
		wantCode  string
		trigger   func(t *testing.T) error
	}{
		{
			name:      "multi_payload_item_is_plan_invalid",
			domainErr: model.ErrInvalid,
			stableErr: planerrors.ErrGatheringPlanInvalid,
			wantCode:  "CIRCLE.USER.gathering_plan_invalid",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-invalid", "host-1")
				items := agendaItems("双 payload 条目")
				items[0].Note = &model.NoteItem{Content: "第二个 payload"}
				_, err := commands.CreateGatheringPlan(
					commandContext("host-1", "create-invalid"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-invalid", Items: items,
						AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "malformed_revision_limit_is_cursor_invalid",
			domainErr: model.ErrCursorInvalid,
			stableErr: planerrors.ErrGatheringPlanCursorInvalid,
			wantCode:  "CIRCLE.USER.gathering_plan_cursor_invalid",
			trigger: func(t *testing.T) error {
				commands, queries := planErrorFacets("gathering-neg-cursor", "host-1")
				var captured error
				handler := planhttp.NewHandler(commands, queries, func(err error) error {
					captured = err
					return planerrors.AppErrorFromGatheringPlanCursorInvalid(err.Error())
				})
				mux := stdhttp.NewServeMux()
				handler.Register(mux)
				recorder := httptest.NewRecorder()
				mux.ServeHTTP(recorder, httptest.NewRequest(
					stdhttp.MethodGet,
					"/gathering-plans/plan-cursor/revisions?limit=abc",
					nil,
				))
				if recorder.Code != stdhttp.StatusBadRequest ||
					!strings.Contains(recorder.Body.String(), "CIRCLE.USER.gathering_plan_cursor_invalid") {
					t.Fatalf(
						"cursor-invalid wire response drift: status=%d body=%s",
						recorder.Code, recorder.Body.String(),
					)
				}
				return captured
			},
		},
		{
			name:      "propose_on_missing_plan_is_not_found",
			domainErr: model.ErrNotFound,
			stableErr: planerrors.ErrGatheringPlanNotFound,
			wantCode:  "CIRCLE.USER.gathering_plan_not_found",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-not-found", "host-1")
				_, err := commands.ProposeGatheringPlan(
					commandContext("host-1", "propose-missing"),
					app.ProposeGatheringPlanCommand{
						PlanID: "gplan_missing", ExpectedPlanVersion: 1,
						Items: agendaItems("不存在计划"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "commit_unknown_proposal_is_proposal_not_found",
			domainErr: model.ErrProposalNotFound,
			stableErr: planerrors.ErrGatheringPlanProposalNotFound,
			wantCode:  "CIRCLE.USER.gathering_plan_proposal_not_found",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-proposal-missing", "host-1")
				created := mustCreateNegativePathPlan(t, commands, "gathering-neg-proposal-missing")
				_, err := commands.CommitGatheringPlanProposal(
					commandContext("host-1", "commit-missing"),
					app.CommitGatheringPlanProposalCommand{
						PlanID: created.PlanID, ProposalID: "gplanprop_missing",
						ExpectedPlanVersion:        created.PlanVersion,
						ExpectedProposalDigest:     "sha256:ffa63583dfa6706b87d284b86b0d693a161e4840aad2c5cf6b5d27c3b9621f7d",
						ExpectedBaseRevisionDigest: created.CurrentRevisionDigest,
					},
				)
				return err
			},
		},
		{
			name:      "second_create_is_already_exists",
			domainErr: model.ErrAlreadyExists,
			stableErr: planerrors.ErrGatheringPlanAlreadyExists,
			wantCode:  "CIRCLE.USER.gathering_plan_already_exists",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-exists", "host-1")
				mustCreateNegativePathPlan(t, commands, "gathering-neg-exists")
				_, err := commands.CreateGatheringPlan(
					commandContext("host-1", "create-again"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-exists",
						Items:       agendaItems("负例基线计划"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "non_host_create_is_permission_denied",
			domainErr: model.ErrPermissionDenied,
			stableErr: planerrors.ErrGatheringPlanPermissionDenied,
			wantCode:  "CIRCLE.USER.gathering_plan_permission_denied",
			trigger: func(t *testing.T) error {
				store := newMemoryPlanStore()
				authority := newAuthorityState()
				authority.set("participant-1", ports.GatheringAuthority{
					GatheringID: "gathering-neg-permission", Exists: true,
					CollaborationOpen: true, ActiveParticipation: true,
				})
				commands := app.NewGatheringPlanCommandFacet(store, authority)
				_, err := commands.CreateGatheringPlan(
					commandContext("participant-1", "create-denied"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-permission",
						Items:       agendaItems("参与者越权创建"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "closed_collaboration_is_gathering_unavailable",
			domainErr: model.ErrGatheringUnavailable,
			stableErr: planerrors.ErrGatheringPlanGatheringUnavailable,
			wantCode:  "CIRCLE.USER.gathering_plan_gathering_unavailable",
			trigger: func(t *testing.T) error {
				store := newMemoryPlanStore()
				authority := newAuthorityState()
				authority.set("host-1", ports.GatheringAuthority{
					GatheringID: "gathering-neg-unavailable", Exists: true,
					CollaborationOpen: false, CurrentHost: true,
				})
				commands := app.NewGatheringPlanCommandFacet(store, authority)
				_, err := commands.CreateGatheringPlan(
					commandContext("host-1", "create-closed"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-unavailable",
						Items:       agendaItems("协作已关闭"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "stale_plan_version_is_version_conflict",
			domainErr: model.ErrVersionConflict,
			stableErr: planerrors.ErrGatheringPlanVersionConflict,
			wantCode:  "CIRCLE.USER.gathering_plan_version_conflict",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-version", "host-1")
				created := mustCreateNegativePathPlan(t, commands, "gathering-neg-version")
				_, err := commands.ProposeGatheringPlan(
					commandContext("host-1", "propose-stale-version"),
					app.ProposeGatheringPlanCommand{
						PlanID: created.PlanID, ExpectedPlanVersion: created.PlanVersion + 7,
						BaseRevisionID:     created.CurrentRevisionID,
						BaseRevisionNumber: created.CurrentRevisionNumber,
						BaseRevisionDigest: created.CurrentRevisionDigest,
						Items:              agendaItems("过期版本提案"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "stale_base_revision_is_revision_conflict",
			domainErr: model.ErrRevisionConflict,
			stableErr: planerrors.ErrGatheringPlanRevisionConflict,
			wantCode:  "CIRCLE.USER.gathering_plan_revision_conflict",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-revision", "host-1")
				created := mustCreateNegativePathPlan(t, commands, "gathering-neg-revision")
				_, err := commands.ProposeGatheringPlan(
					commandContext("host-1", "propose-stale-base"),
					app.ProposeGatheringPlanCommand{
						PlanID: created.PlanID, ExpectedPlanVersion: created.PlanVersion,
						BaseRevisionID:     created.CurrentRevisionID,
						BaseRevisionNumber: created.CurrentRevisionNumber,
						BaseRevisionDigest: "sha256:stale-base-digest",
						Items:              agendaItems("过期基线提案"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "drifted_proposal_digest_is_proposal_conflict",
			domainErr: model.ErrProposalConflict,
			stableErr: planerrors.ErrGatheringPlanProposalConflict,
			wantCode:  "CIRCLE.USER.gathering_plan_proposal_conflict",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-proposal-drift", "host-1")
				created := mustCreateNegativePathPlan(t, commands, "gathering-neg-proposal-drift")
				proposed, err := commands.ProposeGatheringPlan(
					commandContext("host-1", "propose-for-drift"),
					app.ProposeGatheringPlanCommand{
						PlanID: created.PlanID, ExpectedPlanVersion: created.PlanVersion,
						BaseRevisionID:     created.CurrentRevisionID,
						BaseRevisionNumber: created.CurrentRevisionNumber,
						BaseRevisionDigest: created.CurrentRevisionDigest,
						Items:              agendaItems("待提交提案"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				if err != nil {
					t.Fatalf("propose baseline: %v", err)
				}
				_, err = commands.CommitGatheringPlanProposal(
					commandContext("host-1", "commit-drift"),
					app.CommitGatheringPlanProposalCommand{
						PlanID: created.PlanID, ProposalID: proposed.ProposalID,
						ExpectedPlanVersion:        proposed.PlanVersion,
						ExpectedProposalDigest:     "sha256:drifted-proposal-digest",
						ExpectedBaseRevisionDigest: proposed.CurrentRevisionDigest,
					},
				)
				return err
			},
		},
		{
			name:      "reused_idempotency_key_is_idempotency_conflict",
			domainErr: model.ErrIdempotencyConflict,
			stableErr: planerrors.ErrGatheringPlanIdempotencyConflict,
			wantCode:  "CIRCLE.USER.gathering_plan_idempotency_conflict",
			trigger: func(t *testing.T) error {
				commands, _ := planErrorFacets("gathering-neg-idempotency", "host-1")
				if _, err := commands.CreateGatheringPlan(
					commandContext("host-1", "create-reused-key"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-idempotency",
						Items:       agendaItems("首个请求"), AcknowledgementPolicy: noAcknowledgement(),
					},
				); err != nil {
					t.Fatalf("first create: %v", err)
				}
				_, err := commands.CreateGatheringPlan(
					commandContext("host-1", "create-reused-key"),
					app.CreateGatheringPlanCommand{
						GatheringID: "gathering-neg-idempotency",
						Items:       agendaItems("同键不同内容"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
		{
			name:      "storage_outage_falls_back_to_plan_storage_failed",
			domainErr: errPlanStorageDown,
			stableErr: planerrors.ErrGatheringPlanStorageFailed,
			wantCode:  "CIRCLE.SYSTEM.gathering_plan_storage_failed",
			trigger: func(t *testing.T) error {
				authority := newAuthorityState()
				authority.set("host-1", ports.GatheringAuthority{
					GatheringID: "gathering-neg-storage", Exists: true,
					CollaborationOpen: true, CurrentHost: true,
				})
				commands := app.NewGatheringPlanCommandFacet(
					&failingPlanStore{err: errPlanStorageDown},
					authority,
				)
				_, err := commands.ProposeGatheringPlan(
					commandContext("host-1", "propose-storage-down"),
					app.ProposeGatheringPlanCommand{
						PlanID: "gplan_storage_down", ExpectedPlanVersion: 1,
						Items: agendaItems("存储失败注入"), AcknowledgementPolicy: noAcknowledgement(),
					},
				)
				return err
			},
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			err := test.trigger(t)
			if !errors.Is(err, test.domainErr) {
				t.Fatalf("domain sentinel = %v, want %v", err, test.domainErr)
			}
			// generated 稳定码哨兵是 cmd/api mapGatheringPlanError 对该 domain
			// sentinel 的映射目标；锚定其码字面量与 errors.yaml 声明一致。
			if got := test.stableErr.Error(); got != test.wantCode {
				t.Fatalf("stable code = %q, want %q", got, test.wantCode)
			}
		})
	}
}

func planErrorFacets(
	gatheringID string,
	hostActor string,
) (*app.GatheringPlanCommandFacet, *app.GatheringPlanQueryFacet) {
	store := newMemoryPlanStore()
	authority := newAuthorityState()
	authority.set(hostActor, ports.GatheringAuthority{
		GatheringID: gatheringID, Exists: true,
		CollaborationOpen: true, CurrentHost: true,
	})
	return app.NewGatheringPlanCommandFacet(store, authority),
		app.NewGatheringPlanQueryFacet(store, authority)
}

func mustCreateNegativePathPlan(
	t *testing.T,
	commands *app.GatheringPlanCommandFacet,
	gatheringID string,
) model.CommandResult {
	t.Helper()
	created, err := commands.CreateGatheringPlan(
		commandContext("host-1", "create-baseline"),
		app.CreateGatheringPlanCommand{
			GatheringID: gatheringID,
			Items:       agendaItems("负例基线计划"), AcknowledgementPolicy: noAcknowledgement(),
		},
	)
	if err != nil {
		t.Fatalf("create baseline plan: %v", err)
	}
	return created
}

type failingPlanStore struct {
	err error
}

func (store *failingPlanStore) Load(
	_ context.Context,
	_ string,
) (model.GatheringPlan, bool, error) {
	return model.GatheringPlan{}, false, store.err
}

func (store *failingPlanStore) Commit(
	_ context.Context,
	_ ports.CommitRequest,
) (ports.CommitReceipt, error) {
	return ports.CommitReceipt{}, store.err
}

var _ ports.AggregateStore = (*failingPlanStore)(nil)
