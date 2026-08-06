// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
// readiness_case: get-call-local
// readiness_case: list-calls-local
package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func TestCallQueryFacadeUsesTypedObjectReader(t *testing.T) {
	session := terminalActiveSession("call-query", "room-query", "caller", "callee")
	store := &queryCallStore{session: session}
	orchestrator := application.NewCallOrchestrator(
		store,
		noopCallStateCache{},
		newTestCallSessionService(t, 17*time.Second, 41*time.Second),
		nil,
		application.AllowRelationshipGateForTest(),
		application.WithCallAccountSecurityGate(
			application.AllowCallAccountSecurityForTest(),
		),
	)
	got, err := orchestrator.GetCall(context.Background(), session.ID, "caller")
	if err != nil || got.ID != session.ID {
		t.Fatalf("GetCall()=%+v err=%v", got, err)
	}
	page, err := orchestrator.ListCalls(
		context.Background(),
		"caller",
		20,
		"cursor-1",
		application.ListCallsFilter{Status: model.StatusInCall, MissedOnly: true},
	)
	if err != nil || len(page.Items) != 1 || page.Items[0].ID != session.ID {
		t.Fatalf("ListCalls()=%+v err=%v", page, err)
	}
	if store.lastUserID != "caller" || store.lastQuery.Limit != 20 ||
		store.lastQuery.Cursor != "cursor-1" ||
		store.lastQuery.Status != model.StatusInCall || !store.lastQuery.MissedOnly {
		t.Fatalf("typed query was not preserved: user=%q query=%+v", store.lastUserID, store.lastQuery)
	}
}

type queryCallStore struct {
	session    *model.CallSession
	lastUserID string
	lastQuery  application.CallHistoryQuery
}

func (*queryCallStore) CreateCall(context.Context, *model.CallSession) error { return nil }

func (store *queryCallStore) FindCallByID(
	_ context.Context,
	id string,
) (*model.CallSession, error) {
	if store.session == nil || store.session.ID != id {
		return nil, nil
	}
	return cloneCallSession(store.session), nil
}

func (*queryCallStore) FindActiveCallForUser(context.Context, string) (*model.CallSession, error) {
	return nil, nil
}

func (*queryCallStore) FindActiveCallsForUsers(
	context.Context,
	[]string,
	int,
) ([]*model.CallSession, error) {
	return nil, nil
}

func (*queryCallStore) FindOverdueRingingCalls(
	context.Context,
	time.Time,
	time.Time,
	int,
) ([]*model.CallSession, error) {
	return nil, nil
}

func (*queryCallStore) Commit(
	context.Context,
	application.CallCommit,
) (application.CallCommitResult, error) {
	return application.CallCommitResult{}, nil
}

func (*queryCallStore) FindReceipt(
	context.Context,
	string,
	string,
	string,
) (application.CallCommitResult, bool, error) {
	return application.CallCommitResult{}, false, nil
}

func (*queryCallStore) RecordNoopReceipt(
	context.Context,
	application.CallNoopReceipt,
) (application.CallCommitResult, error) {
	return application.CallCommitResult{}, nil
}

func (store *queryCallStore) ListCallsByUserID(
	_ context.Context,
	userID string,
	query application.CallHistoryQuery,
) (application.CallHistoryPage, error) {
	store.lastUserID = userID
	store.lastQuery = query
	return application.CallHistoryPage{
		Items:      []*model.CallSession{cloneCallSession(store.session)},
		NextCursor: "cursor-2",
	}, nil
}
