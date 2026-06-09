package application

import (
	"context"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	wsadapter "quwoquan_service/services/rtc-service/internal/adapters/ws"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	"quwoquan_service/services/rtc-service/internal/generated"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/event"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
	"quwoquan_service/services/rtc-service/internal/infrastructure/cache"
	"quwoquan_service/services/rtc-service/internal/infrastructure/persistence"
)

type CallOrchestrator struct {
	repo           persistence.CallRepository
	cache          *cache.CallStateCache
	domainService  *callsession.CallSessionService
	roomService    *RoomService
	tokenService   *TokenService
	eventPublisher *mq.EventPublisher
	signalHandler  *wsadapter.SignalHandler
	relationships  RelationshipGate
}

func NewCallOrchestrator(
	repo persistence.CallRepository,
	cache *cache.CallStateCache,
	domainSvc *callsession.CallSessionService,
	roomSvc *RoomService,
	tokenSvc *TokenService,
	eventPub *mq.EventPublisher,
	relationships RelationshipGate,
	sigHandler ...*wsadapter.SignalHandler,
) *CallOrchestrator {
	if relationships == nil {
		relationships = DenyRelationshipGate()
	}
	o := &CallOrchestrator{
		repo:           repo,
		cache:          cache,
		domainService:  domainSvc,
		roomService:    roomSvc,
		tokenService:   tokenSvc,
		eventPublisher: eventPub,
		relationships:  relationships,
	}
	if len(sigHandler) > 0 {
		o.signalHandler = sigHandler[0]
	}
	return o
}

type InitiateCallRequest struct {
	InitiatorID    string   `json:"initiatorId"`
	CallType       string   `json:"callType"`
	ConversationID string   `json:"conversationId"`
	CircleID       string   `json:"circleId"`
	InviteeIDs     []string `json:"inviteeIds"`
}

type InitiateCallResponse struct {
	Session *model.CallSession `json:"session"`
	Token   string             `json:"token"`
}

func (o *CallOrchestrator) InitiateCall(ctx context.Context, req InitiateCallRequest) (*InitiateCallResponse, error) {
	existingCallID, _ := o.cache.GetActiveCallForUser(ctx, req.InitiatorID)
	if existingCallID != "" {
		return nil, generated.AppErrorFromAlreadyInCall("user already in active call")
	}
	if err := o.ensureOneToOneRelationshipGate(ctx, req); err != nil {
		return nil, err
	}

	session, err := o.domainService.InitiateCall(req.InitiatorID, req.CallType, req.ConversationID, req.CircleID, req.InviteeIDs)
	if err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("initiate: " + err.Error())
	}

	session.ID = generateID()
	session.RoomID = "rtc-room-" + session.ID

	if o.roomService != nil {
		_ = o.roomService.CreateRoom(ctx, session.RoomID, session.MaxParticipants)
	}

	if err := o.repo.CreateCall(ctx, session); err != nil {
		return nil, generated.AppErrorFromInternalError("persist call: " + err.Error())
	}

	_ = o.cache.SetCallState(ctx, session)
	_ = o.cache.SetActiveCallForUser(ctx, req.InitiatorID, session.ID)
	_ = o.cache.SetCallTimeout(ctx, session.ID, 0)

	o.domainService.SetRinging(session)
	_ = o.repo.UpdateCall(ctx, session)
	_ = o.cache.SetCallState(ctx, session)

	o.publishEvent(ctx, event.CallInitiated, session, req.InitiatorID, nil)
	o.publishEvent(ctx, event.CallRinging, session, req.InitiatorID, nil)

	token := ""
	if o.tokenService != nil {
		token, _ = o.tokenService.GenerateParticipantToken(session.RoomID, req.InitiatorID)
	}

	return &InitiateCallResponse{Session: session, Token: token}, nil
}

type AnswerCallResponse struct {
	Session *model.CallSession `json:"session"`
	Token   string             `json:"token"`
	RoomID  string             `json:"roomId"`
}

func (o *CallOrchestrator) AnswerCall(ctx context.Context, callID, userID string) (*AnswerCallResponse, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.AnswerCall(session, userID); err != nil {
		return nil, generated.AppErrorFromCannotAnswer(err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	_ = o.cache.SetActiveCallForUser(ctx, userID, callID)
	_ = o.cache.DeleteCallTimeout(ctx, callID)

	token := ""
	if o.tokenService != nil {
		token, _ = o.tokenService.GenerateParticipantToken(session.RoomID, userID)
	}

	o.publishEvent(ctx, event.CallAnswered, session, userID, nil)
	return &AnswerCallResponse{Session: session, Token: token, RoomID: session.RoomID}, nil
}

func (o *CallOrchestrator) RejectCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.RejectCall(session, userID); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("reject: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.cleanupIfEnded(ctx, session)
	o.publishEvent(ctx, event.CallEnded, session, userID, map[string]any{"reason": session.EndReason})
	return session, nil
}

func (o *CallOrchestrator) CancelCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.CancelCall(session, userID); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("cancel: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.cleanupIfEnded(ctx, session)
	o.publishEvent(ctx, event.CallEnded, session, userID, map[string]any{"reason": session.EndReason})
	return session, nil
}

func (o *CallOrchestrator) HangupCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.HangupCall(session, userID); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("hangup: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	_ = o.cache.DeleteActiveCallForUser(ctx, userID)
	o.cleanupIfEnded(ctx, session)

	if session.Status == model.StatusEnded {
		o.publishEvent(ctx, event.CallEnded, session, userID, map[string]any{"reason": session.EndReason})
	} else {
		o.publishEvent(ctx, event.ParticipantLeft, session, userID, nil)
	}
	return session, nil
}

func (o *CallOrchestrator) JoinCall(ctx context.Context, callID, userID string) (*model.CallSession, string, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, "", err
	}
	if err := o.domainService.JoinCall(session, userID); err != nil {
		return nil, "", generated.AppErrorFromInvalidCallAction("join: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, "", wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	_ = o.cache.SetActiveCallForUser(ctx, userID, callID)

	token := ""
	if o.tokenService != nil {
		token, _ = o.tokenService.GenerateParticipantToken(session.RoomID, userID)
	}

	o.publishEvent(ctx, event.ParticipantJoined, session, userID, nil)
	return session, token, nil
}

func (o *CallOrchestrator) LeaveCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.LeaveCall(session, userID); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("leave: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	_ = o.cache.DeleteActiveCallForUser(ctx, userID)

	if o.roomService != nil {
		_ = o.roomService.RemoveParticipant(ctx, session.RoomID, userID)
	}

	o.cleanupIfEnded(ctx, session)
	o.publishEvent(ctx, event.ParticipantLeft, session, userID, nil)
	return session, nil
}

type InviteToCallRequest struct {
	InviteeIDs []string `json:"inviteeIds"`
}

func (o *CallOrchestrator) InviteToCall(ctx context.Context, callID, userID string, inviteeIDs []string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.InviteToCall(session, inviteeIDs); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("invite: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)

	o.publishEvent(ctx, event.CallRinging, session, userID, map[string]any{"inviteeIds": inviteeIDs})
	return session, nil
}

func (o *CallOrchestrator) GetCall(ctx context.Context, callID string) (*model.CallSession, error) {
	return o.loadSession(ctx, callID)
}

// ListCallsFilter 表达通话记录列表的筛选条件（与 service.yaml ListCalls query_params 对齐）。
type ListCallsFilter struct {
	// Status 仅返回该状态的通话（空表示不限）。
	Status string
	// MissedOnly 为 true 时仅返回对 userID 而言的未接来电。
	MissedOnly bool
}

func (o *CallOrchestrator) ListCalls(ctx context.Context, userID string, limit int, cursor string, filter ListCallsFilter) ([]*model.CallSession, error) {
	calls, err := o.repo.ListCallsByUserID(ctx, userID, limit, cursor)
	if err != nil {
		return nil, err
	}
	if filter.Status == "" && !filter.MissedOnly {
		return calls, nil
	}
	filtered := make([]*model.CallSession, 0, len(calls))
	for _, c := range calls {
		if filter.Status != "" && c.Status != filter.Status {
			continue
		}
		if filter.MissedOnly && !c.IsMissedFor(userID) {
			continue
		}
		filtered = append(filtered, c)
	}
	return filtered, nil
}

type ToggleMuteRequest struct {
	Muted bool `json:"muted"`
}

func (o *CallOrchestrator) ToggleMute(ctx context.Context, callID, userID string, muted bool) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.ToggleMute(session, userID, muted); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("toggle mute: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	return session, nil
}

type ToggleCameraRequest struct {
	CameraOn bool `json:"cameraOn"`
}

func (o *CallOrchestrator) ToggleCamera(ctx context.Context, callID, userID string, cameraOn bool) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.ToggleCamera(session, userID, cameraOn); err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("toggle camera: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	return session, nil
}

func (o *CallOrchestrator) StartRecording(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.StartRecording(session, userID); err != nil {
		return nil, generated.AppErrorFromRecordingNotAllowed("start recording: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.publishEvent(ctx, event.CallRecordingStarted, session, userID, nil)
	return session, nil
}

func (o *CallOrchestrator) StopRecording(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.StopRecording(session, userID); err != nil {
		return nil, generated.AppErrorFromRecordingNotAllowed("stop recording: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.publishEvent(ctx, event.CallRecordingStopped, session, userID, nil)
	return session, nil
}

func (o *CallOrchestrator) StartScreenShare(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.StartScreenShare(session, userID); err != nil {
		return nil, generated.AppErrorFromScreenShareConflict("start screen share: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.publishEvent(ctx, event.ScreenShareStarted, session, userID, nil)
	return session, nil
}

func (o *CallOrchestrator) StopScreenShare(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if err := o.domainService.StopScreenShare(session, userID); err != nil {
		return nil, generated.AppErrorFromScreenShareConflict("stop screen share: " + err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.publishEvent(ctx, event.ScreenShareStopped, session, userID, nil)
	return session, nil
}

func (o *CallOrchestrator) ensureOneToOneRelationshipGate(ctx context.Context, req InitiateCallRequest) error {
	if strings.TrimSpace(req.CircleID) != "" || len(req.InviteeIDs) != 1 {
		return nil
	}
	peerID := strings.TrimSpace(req.InviteeIDs[0])
	if peerID == "" {
		return nil
	}
	capability, err := o.relationships.GetCapability(ctx, req.InitiatorID, peerID)
	if err != nil {
		return err
	}
	if capability.IsBlocked || capability.IsBlockedBy {
		return generated.AppErrorFromBlocked("one-to-one call blocked by relationship gate")
	}
	if !capability.IsMutual {
		return generated.AppErrorFromNotMutual("one-to-one call requires mutual follow")
	}
	return nil
}

func (o *CallOrchestrator) loadSession(ctx context.Context, callID string) (*model.CallSession, error) {
	cached, _ := o.cache.GetCallState(ctx, callID)
	if cached != nil {
		return cached, nil
	}
	session, err := o.repo.FindCallByID(ctx, callID)
	if err != nil {
		return nil, generated.AppErrorFromCallNotFound("call not found: " + callID)
	}
	_ = o.cache.SetCallState(ctx, session)
	return session, nil
}

func (o *CallOrchestrator) cleanupIfEnded(ctx context.Context, session *model.CallSession) {
	if session.Status != model.StatusEnded {
		return
	}
	for _, p := range session.Participants {
		_ = o.cache.DeleteActiveCallForUser(ctx, p.UserID)
	}
	_ = o.cache.DeleteCallTimeout(ctx, session.ID)
	if o.roomService != nil {
		_ = o.roomService.DeleteRoom(ctx, session.RoomID)
	}
}

func (o *CallOrchestrator) publishEvent(ctx context.Context, eventType string, session *model.CallSession, actorID string, payload map[string]any) {
	if payload == nil {
		payload = map[string]any{}
	}
	payload["status"] = session.Status
	payload["participantCount"] = session.ParticipantCount

	if o.eventPublisher != nil {
		_ = o.eventPublisher.Publish(ctx, mq.DomainEvent{
			Type:      eventType,
			CallID:    session.ID,
			ActorID:   actorID,
			Timestamp: time.Now(),
			Payload:   payload,
		})
	}

	if o.signalHandler != nil {
		wsEvent := map[string]any{
			"type":    signalWireType(eventType),
			"callId":  session.ID,
			"actorId": actorID,
			"payload": payload,
		}
		if eventType == event.CallRinging || eventType == event.CallInitiated {
			for _, p := range session.Participants {
				if p.UserID != actorID {
					o.signalHandler.PushToUser(ctx, p.UserID, wsEvent)
				}
			}
		} else {
			userIDs := make([]string, 0, len(session.Participants))
			for _, p := range session.Participants {
				userIDs = append(userIDs, p.UserID)
			}
			o.signalHandler.PushToUsers(ctx, userIDs, wsEvent)
		}
	}
}

func wrapSystemError(err error) *rterr.AppError {
	return generated.AppErrorFromInternalError(err.Error())
}
