// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// GatheringSafety 授权链路声明错误码的负例断言：每个用例真实驱动
// ReportService 拒绝路径到 generated AppError 工厂的 emit 点，
// 并以字面 wire code 锁定端云契约。
package report_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	reportapp "quwoquan_service/services/content-service/internal/trust_safety/report/application"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

// errSemSafetyStore 只覆盖授权端口以注入领域 sentinel，其余 Report
// 端口继续由对象 testsupport Store 提供真实实现。
type errSemSafetyStore struct {
	*testsupport.ReportStore
	issueErr error
}

func (store *errSemSafetyStore) IssueGatheringSafetyAuthorization(
	context.Context,
	reportports.IssueGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	return reportports.GatheringSafetyAuthorization{}, false, store.issueErr
}

func (store *errSemSafetyStore) RevokeGatheringSafetyAuthorization(
	context.Context,
	reportports.RevokeGatheringSafetyAuthorizationRequest,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	return reportports.GatheringSafetyAuthorization{}, false, store.issueErr
}

func (store *errSemSafetyStore) ReadGatheringSafetyAuthorization(
	context.Context,
	string,
) (reportports.GatheringSafetyAuthorization, bool, error) {
	return reportports.GatheringSafetyAuthorization{}, false, nil
}

func newErrSemSafetyService(issueErr error) *reportapp.ReportService {
	return reportapp.NewReportService(reportapp.BindDataPorts(&errSemSafetyStore{
		ReportStore: testsupport.NewReportStore(),
		issueErr:    issueErr,
	}))
}

func requireSafetyAppErrorCode(t *testing.T, err error, wantCode string) {
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

func validSafetyGrantCommand() reportapp.GrantGatheringSafetyTerminationCommand {
	return reportapp.GrantGatheringSafetyTerminationCommand{
		ReportID:              "report-err-sem",
		ExpectedReportVersion: 3,
		ActorPersonaID:        "persona-safety",
		ExpiresAt:             time.Now().UTC().Add(2 * time.Minute),
		IdempotencyKey:        "grant-err-sem",
	}
}

func TestGrantWithoutReportIDEmitsGatheringSafetyAuthorizationInvalid(t *testing.T) {
	service := newErrSemSafetyService(nil)
	command := validSafetyGrantCommand()
	command.ReportID = ""
	_, err := service.GrantGatheringSafetyTermination(context.Background(), command)
	requireSafetyAppErrorCode(t, err, "CONTENT.USER.gathering_safety_authorization_invalid")
}

func TestGrantDeniedByAuthorityEmitsGatheringSafetyAuthorizationDenied(t *testing.T) {
	service := newErrSemSafetyService(reportports.ErrGatheringSafetyAuthorizationDenied)
	_, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		validSafetyGrantCommand(),
	)
	requireSafetyAppErrorCode(t, err, "CONTENT.USER.gathering_safety_authorization_denied")
}

func TestGrantConcurrentDecisionEmitsGatheringSafetyAuthorizationConflict(t *testing.T) {
	service := newErrSemSafetyService(reportports.ErrGatheringSafetyAuthorizationConflict)
	_, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		validSafetyGrantCommand(),
	)
	requireSafetyAppErrorCode(t, err, "CONTENT.USER.gathering_safety_authorization_conflict")
}

func TestGrantWithFailingAuthorityEmitsGatheringSafetyAuthorityUnavailable(t *testing.T) {
	service := newErrSemSafetyService(errors.New("authority database unavailable"))
	_, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		validSafetyGrantCommand(),
	)
	requireSafetyAppErrorCode(t, err, "CONTENT.SYSTEM.gathering_safety_authority_unavailable")
}

func TestGrantForAbsentReportEmitsReportNotFound(t *testing.T) {
	service := newErrSemSafetyService(reportports.ErrGatheringSafetyAuthorizationNotFound)
	_, err := service.GrantGatheringSafetyTermination(
		context.Background(),
		validSafetyGrantCommand(),
	)
	requireSafetyAppErrorCode(t, err, "CONTENT.USER.report_not_found")
}
