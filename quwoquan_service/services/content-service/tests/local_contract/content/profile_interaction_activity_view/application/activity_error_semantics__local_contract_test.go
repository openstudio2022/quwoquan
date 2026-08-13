// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// ProfileInteractionActivityView 声明错误码的负例断言：每个用例真实驱动
// ActivityQueryService 拒绝路径到 generated AppError 工厂的 emit 点，
// 并以字面 wire code 锁定端云契约。
package profileinteraction_test

import (
	"context"
	"errors"
	"testing"

	rterr "quwoquan_service/runtime/errors"
	activityapp "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/application"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
)

type errSemActivityReader struct {
	err error
}

func (r errSemActivityReader) List(
	context.Context,
	activityports.PageRequest,
) (activityports.Page, error) {
	if r.err != nil {
		return activityports.Page{}, r.err
	}
	return activityports.Page{}, nil
}

func (r errSemActivityReader) CanAppendReadFact(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

func requireActivityAppErrorCode(t *testing.T, err error, wantCode string) {
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

func TestListActivitiesWithUnknownTypeEmitsInteractionTypeInvalid(t *testing.T) {
	service := activityapp.NewActivityQueryService(errSemActivityReader{})
	_, err := service.ListActivities(context.Background(), activityapp.ActivityPageQuery{
		OwnerPersonaID:  "persona-owner",
		ViewerPersonaID: "persona-owner",
		Direction:       "received",
		ActivityType:    "poke",
	})
	requireActivityAppErrorCode(t, err, "CONTENT.USER.interaction_type_invalid")
}

func TestListShareActivitiesByForeignViewerEmitsInteractionOwnerForbidden(t *testing.T) {
	service := activityapp.NewActivityQueryService(errSemActivityReader{})
	_, err := service.ListActivities(context.Background(), activityapp.ActivityPageQuery{
		OwnerPersonaID:  "persona-owner",
		ViewerPersonaID: "persona-viewer",
		Direction:       "sent",
		ActivityType:    "share",
	})
	requireActivityAppErrorCode(t, err, "CONTENT.USER.interaction_owner_forbidden")
}

func TestListActivitiesWithMalformedCursorEmitsInteractionCursorInvalid(t *testing.T) {
	service := activityapp.NewActivityQueryService(errSemActivityReader{})
	_, err := service.ListActivities(context.Background(), activityapp.ActivityPageQuery{
		OwnerPersonaID:  "persona-owner",
		ViewerPersonaID: "persona-owner",
		Direction:       "received",
		ActivityType:    "like",
		Cursor:          "!!!not-base64!!!",
	})
	requireActivityAppErrorCode(t, err, "CONTENT.USER.interaction_cursor_invalid")
}

func TestListActivitiesWithFailingReaderEmitsInteractionReadModelUnavailable(t *testing.T) {
	service := activityapp.NewActivityQueryService(errSemActivityReader{
		err: errors.New("interaction projection store unreachable"),
	})
	_, err := service.ListActivities(context.Background(), activityapp.ActivityPageQuery{
		OwnerPersonaID:  "persona-owner",
		ViewerPersonaID: "persona-owner",
		Direction:       "received",
		ActivityType:    "like",
	})
	requireActivityAppErrorCode(t, err, "CONTENT.SYSTEM.interaction_read_model_unavailable")
}
