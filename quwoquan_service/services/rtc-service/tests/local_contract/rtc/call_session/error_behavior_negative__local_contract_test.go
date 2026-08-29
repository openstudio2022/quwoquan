// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
//
// call_session 错误行为负例：经真实 CallOrchestrator（typed double store/
// gate/media provider）触发 errors.yaml 声明的错误码，断言 AppError 的
// wire code 与 http_status 与契约一致。
package local_contract

import (
	"context"
	"errors"
	"net/http"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	application "quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application/commandmeta"
	model "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

// negativeCallContext 提供命令幂等键；replay 检查发生在多数错误点之前。
func negativeCallContext(key string) context.Context {
	return commandmeta.WithIdempotencyKey(context.Background(), key)
}

// activeCallStore 让 FindActiveCallForUser 返回既有会话，驱动 already_in_call。
type activeCallStore struct {
	queryCallStore
	active *model.CallSession
	err    error
}

func (store *activeCallStore) FindActiveCallForUser(
	context.Context, string,
) (*model.CallSession, error) {
	return store.active, store.err
}

// failingMediaProvider 注入 SFU 房间创建失败，驱动 media_transport_unavailable。
type failingMediaProvider struct{}

var errMediaDown = errors.New("injected media transport failure")

func (failingMediaProvider) CreateRoom(context.Context, string, int) error {
	return errMediaDown
}

func (failingMediaProvider) DeleteRoom(context.Context, string) error { return nil }

func (failingMediaProvider) ListParticipants(
	context.Context, string,
) ([]application.RoomParticipant, error) {
	return nil, errMediaDown
}

func (failingMediaProvider) RemoveParticipant(context.Context, string, string) error {
	return nil
}

func (failingMediaProvider) IssueParticipantAccess(
	context.Context, string, string,
) (application.MediaSessionAccess, error) {
	return application.MediaSessionAccess{}, errMediaDown
}

// stubSecurityGate 注入账号安全权威的拒绝/不可用两种失败。
type stubSecurityGate struct {
	err error
}

func (g stubSecurityGate) AuthorizeCallActor(context.Context, string) error {
	return g.err
}

// allowAllRelationshipGate 放行互关校验，让链路走到后续错误点。
type allowAllRelationshipGate struct{}

func (allowAllRelationshipGate) GetCapability(
	context.Context, string, string,
) (application.RelationshipCapability, error) {
	return application.RelationshipCapability{IsMutual: true}, nil
}

type blockedRelationshipGate struct {
	capability application.RelationshipCapability
}

func (gate blockedRelationshipGate) GetCapability(
	context.Context, string, string,
) (application.RelationshipCapability, error) {
	return gate.capability, nil
}

func negativeOrchestrator(
	t *testing.T,
	store application.CallStore,
	media application.MediaRoomProvider,
	relationships application.RelationshipGate,
	security application.CallAccountSecurityGate,
) *application.CallOrchestrator {
	t.Helper()
	options := []application.CallOrchestratorOption{}
	if security != nil {
		options = append(options, application.WithCallAccountSecurityGate(security))
	} else {
		options = append(
			options,
			application.WithCallAccountSecurityGate(application.AllowCallAccountSecurityForTest()),
		)
	}
	return application.NewCallOrchestrator(
		store,
		noopCallStateCache{},
		newTestCallSessionService(t, 17*time.Second, 41*time.Second),
		media,
		relationships,
		options...,
	)
}

func assertCallAppError(t *testing.T, err error, wantCode string, wantStatus int) {
	t.Helper()
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("err = %v, want *AppError with code %s", err, wantCode)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("code = %s, want %s", appErr.Code.String(), wantCode)
	}
	if appErr.HTTPStatus != wantStatus {
		t.Fatalf("http status = %d, want %d", appErr.HTTPStatus, wantStatus)
	}
}

func directCallRequest(initiator, invitee string) application.InitiateCallRequest {
	return application.InitiateCallRequest{
		InitiatorID:     initiator,
		InviteeIDs:      []string{invitee},
		CallType:        string(model.CallTypeAudio),
		MaxParticipants: model.MaxParticipants1v1,
	}
}

func TestInitiateWithoutPersonaEmitsUnauthorized(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("", "callee"),
	)
	assertCallAppError(t, err, "RTC.USER.unauthorized", http.StatusUnauthorized)
}

func TestInitiateActiveLookupFailureEmitsInternalError(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t,
		&activeCallStore{err: errors.New("injected store failure")},
		nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(t, err, "RTC.SYSTEM.internal_error", http.StatusInternalServerError)
}

func TestInitiateWhileActiveEmitsAlreadyInCall(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t,
		&activeCallStore{active: terminalActiveSession("call-busy", "room-busy", "caller", "peer")},
		nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(t, err, "RTC.USER.already_in_call", http.StatusConflict)
}

func TestInitiateBlockedRelationshipEmitsBlocked(t *testing.T) {
	t.Parallel()
	for _, testCase := range []struct {
		name       string
		capability application.RelationshipCapability
	}{
		{
			name:       "caller_blocks_callee",
			capability: application.RelationshipCapability{IsBlocked: true},
		},
		{
			name:       "callee_blocks_caller",
			capability: application.RelationshipCapability{IsBlockedBy: true},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			orchestrator := negativeOrchestrator(
				t,
				&queryCallStore{},
				nil,
				blockedRelationshipGate{capability: testCase.capability},
				nil,
			)
			_, err := orchestrator.InitiateCall(
				negativeCallContext("neg-key-"+testCase.name),
				directCallRequest("caller", "callee"),
			)
			assertCallAppError(t, err, "RTC.USER.blocked", http.StatusForbidden)
		})
	}
}

func TestInitiateWithoutMutualFollowEmitsNotMutual(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, nil, application.DenyRelationshipGate(), nil,
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(t, err, "RTC.USER.not_mutual", http.StatusForbidden)
}

func TestInitiateWithFailingSFUEmitsMediaTransportUnavailable(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, failingMediaProvider{}, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(
		t, err, "RTC.SYSTEM.media_transport_unavailable", http.StatusServiceUnavailable,
	)
}

func TestInitiateWithDeniedSecurityAuthorityEmitsAccountSecurityDenied(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, nil, allowAllRelationshipGate{},
		stubSecurityGate{err: application.ErrCallAccountSecurityDenied},
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(
		t, err, "RTC.USER.account_security_denied", http.StatusUnauthorized,
	)
}

func TestInitiateWithUnavailableSecurityAuthorityEmitsAccountSecurityUnavailable(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, nil, allowAllRelationshipGate{},
		stubSecurityGate{err: errors.New("injected security authority outage")},
	)
	_, err := orchestrator.InitiateCall(
		negativeCallContext("neg-key"), directCallRequest("caller", "callee"),
	)
	assertCallAppError(
		t, err, "RTC.SYSTEM.account_security_unavailable", http.StatusServiceUnavailable,
	)
}

func TestHangupUnknownCallEmitsCallNotFound(t *testing.T) {
	t.Parallel()
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.HangupCall(negativeCallContext("neg-key"), "call-missing", "caller")
	assertCallAppError(t, err, "RTC.USER.call_not_found", http.StatusNotFound)
}

func TestHangupByOutsiderEmitsNotParticipant(t *testing.T) {
	t.Parallel()
	session := terminalActiveSession("call-outsider", "room-outsider", "caller", "peer")
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{session: session}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.HangupCall(negativeCallContext("neg-key"), session.ID, "intruder")
	assertCallAppError(t, err, "RTC.USER.not_participant", http.StatusForbidden)
}

func TestJoinEndedCallEmitsCallEnded(t *testing.T) {
	t.Parallel()
	session := terminalActiveSession("call-ended", "room-ended", "caller", "peer")
	session.Status = model.StatusEnded
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{session: session}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.JoinCall(negativeCallContext("neg-key"), session.ID, "caller")
	assertCallAppError(t, err, "RTC.USER.call_ended", http.StatusGone)
}

func TestAnswerInCallSessionEmitsCannotAnswer(t *testing.T) {
	t.Parallel()
	session := terminalActiveSession("call-answered", "room-answered", "caller", "peer")
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{session: session}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.AnswerCall(negativeCallContext("neg-key"), session.ID, "peer")
	assertCallAppError(t, err, "RTC.USER.cannot_answer", http.StatusConflict)
}

func TestRejectInCallSessionEmitsInvalidCallAction(t *testing.T) {
	t.Parallel()
	session := terminalActiveSession("call-reject", "room-reject", "caller", "peer")
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{session: session}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.RejectCall(negativeCallContext("neg-key"), session.ID, "peer")
	assertCallAppError(t, err, "RTC.USER.invalid_call_action", http.StatusConflict)
}

func TestStartScreenShareOverForeignShareEmitsScreenShareConflict(t *testing.T) {
	t.Parallel()
	session := terminalActiveSession("call-share", "room-share", "caller", "peer")
	session.IsScreenSharing = true
	session.ScreenShareUserID = "caller"
	orchestrator := negativeOrchestrator(
		t, &queryCallStore{session: session}, nil, allowAllRelationshipGate{}, nil,
	)
	_, err := orchestrator.StartScreenShare(negativeCallContext("neg-key"), session.ID, "peer")
	assertCallAppError(
		t, err, "RTC.USER.screen_share_conflict", http.StatusConflict,
	)
}
