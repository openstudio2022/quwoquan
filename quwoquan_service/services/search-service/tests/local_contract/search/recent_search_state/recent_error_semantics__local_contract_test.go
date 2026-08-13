// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// RecentSearchState 声明错误码的负例断言：以对象级 typed Store double 驱动
// 存储失败与 CAS 版本冲突耗尽路径，以字面 wire code 锁定端云契约。
package local_contract

import (
	"context"
	"errors"
	"testing"

	rterrors "quwoquan_service/runtime/errors"
	application "quwoquan_service/services/search-service/internal/search/recent_search_state/application"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/model"
	"quwoquan_service/services/search-service/internal/search/recent_search_state/domain/ports"
)

type errSemRecentStore struct {
	loadErr   error
	commitErr error
}

func (s errSemRecentStore) Load(
	context.Context, string, string,
) (model.State, bool, error) {
	if s.loadErr != nil {
		return model.State{}, false, s.loadErr
	}
	return model.State{}, false, nil
}

func (s errSemRecentStore) ListByPersona(
	context.Context, string,
) ([]model.State, error) {
	return nil, nil
}

func (s errSemRecentStore) FindEntryOwner(
	context.Context, string, string,
) (model.State, bool, error) {
	return model.State{}, false, nil
}

func (s errSemRecentStore) FindReceipt(
	context.Context, string, string,
) (ports.Receipt, bool, error) {
	return ports.Receipt{}, false, nil
}

func (s errSemRecentStore) Commit(context.Context, ports.Commit) error {
	return s.commitErr
}

func (s errSemRecentStore) RecordNoopReceipt(
	_ context.Context, receipt ports.Receipt,
) (ports.Receipt, error) {
	return receipt, nil
}

func errSemUpsert(t *testing.T, store ports.Store) error {
	t.Helper()
	facade, err := application.NewFacade(store)
	if err != nil {
		t.Fatalf("new recent facade: %v", err)
	}
	_, err = facade.Upsert(context.Background(), application.UpsertCommand{
		PersonaID:      "persona-errsem",
		Query:          "苍山洱海",
		IdempotencyKey: "recent-errsem-key",
	})
	return err
}

func requireRecentAppErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rterrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func TestRecentUpsertLoadFailureEmitsRecentStorageFailed(t *testing.T) {
	err := errSemUpsert(t, errSemRecentStore{
		loadErr: errors.New("mongo find timed out"),
	})
	requireRecentAppErrorCode(t, err, "SEARCH.SYSTEM.recent_storage_failed")
}

func TestRecentUpsertExhaustedVersionConflictEmitsRecentVersionConflict(t *testing.T) {
	err := errSemUpsert(t, errSemRecentStore{
		commitErr: ports.ErrVersionConflict,
	})
	requireRecentAppErrorCode(t, err, "SEARCH.USER.recent_version_conflict")
}
