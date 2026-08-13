// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
//
// 为 gathering errors.yaml 中只能在 application facade 层触发的稳定错误码
// 补真实断言：依赖失败注入（target reader / aggregate store）与 viewer 授权
// 负例都经生产 facade 真实走 mapLifecycleError / query 授权分支，断言
// canonical AppError 的稳定码（与 gathering_withdraw_application 的
// assertWithdrawErrorCode 同形态）。
package application_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestCreateGatheringDraftMapsUnreachableSourceToTargetUnavailable(t *testing.T) {
	facade := app.NewLifecycleFacade(
		newScopeACommitStore(),
		unavailableTargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	command := scopeACreateCommand(time.Now().UTC())
	command.Purpose.SourceObjectRefs = []contract.GatheringSourceRef{{
		ObjectRef: contract.CanonicalObjectRef{
			ObjectTypeRef: "content.post",
			ObjectID:      "post-unreachable",
		},
		RouteID:      "content_post_detail",
		SourceDigest: "source-digest-unreachable",
	}}
	_, err := facade.CreateGatheringDraft(
		scopeACommandContext("create-target-unavailable"),
		command,
	)
	assertGatheringStableCode(t, err, "CIRCLE.DEPENDENCY.gathering_target_unavailable")
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
func TestLifecycleFacadeMapsUnknownStoreFailureToGatheringStorageFailed(t *testing.T) {
	facade := app.NewLifecycleFacade(
		&erroringLifecycleStore{err: errors.New("mongo write concern timeout")},
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	_, err := facade.PublishGathering(
		scopeACommandContext("publish-storage-failed"),
		app.GatheringVersionCommand{
			GatheringID:              "gathering-storage-failed",
			ExpectedGatheringVersion: 1,
		},
	)
	assertGatheringStableCode(t, err, "CIRCLE.SYSTEM.gathering_storage_failed")
}

// mapLifecycleError 是 gathering_control_required 的唯一 canonical 出口；
// errors.yaml 将其声明给 PublishGathering / SafetyTerminateGathering。此处
// 经聚合 mutation 错误传播真实走该映射分支，锚定稳定码与恢复语义不漂移。
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
func TestLifecycleFacadeMapsControlRequiredSentinelToCanonicalCode(t *testing.T) {
	facade := app.NewLifecycleFacade(
		&erroringLifecycleStore{err: gatheringerrors.ErrGatheringControlRequired},
		scopeATargetReader{},
		scopeAHostAuthority{},
		&scopeAParticipationHook{},
		scopeAOutcomeCalculator{},
		scopeAAllowSafetyAuthorizer{},
	)
	_, err := facade.PublishGathering(
		scopeACommandContext("publish-control-required"),
		app.GatheringVersionCommand{
			GatheringID:              "gathering-control-required",
			ExpectedGatheringVersion: 1,
		},
	)
	assertGatheringStableCode(t, err, "CIRCLE.USER.gathering_control_required")
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
func TestGetGatheringForClosedParticipationIsAccessRevoked(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	value.Participations = append(value.Participations, app.ParticipationRecord{
		PersonaID:    "persona-revoked",
		State:        "closed",
		ClosedReason: "removed",
		Version:      2,
	})
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	_, err := facade.GetGathering(
		personaContext("persona-revoked"),
		app.GatheringIDQuery{GatheringID: value.ID},
	)
	assertGatheringStableCode(t, err, "CIRCLE.USER.gathering_access_revoked")
}

func assertGatheringStableCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error is not canonical AppError: %T %v", err, err)
	}
	if got := appError.Code.String(); got != wantCode {
		t.Fatalf("stable error code = %q, want %q", got, wantCode)
	}
}

type unavailableTargetReader struct{}

func (unavailableTargetReader) RequireNavigable(
	context.Context,
	contract.GatheringSourceRef,
) error {
	return errors.New("source object owner is unreachable")
}

type erroringLifecycleStore struct {
	err error
}

func (store *erroringLifecycleStore) Load(
	context.Context,
	string,
) (model.Gathering, bool, error) {
	return model.Gathering{}, false, nil
}

func (store *erroringLifecycleStore) Commit(
	context.Context,
	ports.CommitRequest,
) (ports.CommitReceipt, error) {
	return ports.CommitReceipt{}, store.err
}

var (
	_ ports.TargetReader   = unavailableTargetReader{}
	_ ports.AggregateStore = (*erroringLifecycleStore)(nil)
)
