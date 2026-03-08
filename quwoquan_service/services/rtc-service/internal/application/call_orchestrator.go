package application

import (
	"context"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/rtc-service/internal/adapters/mq"
	wsadapter "quwoquan_service/services/rtc-service/internal/adapters/ws"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
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
}

func NewCallOrchestrator(
	repo persistence.CallRepository,
	cache *cache.CallStateCache,
	domainSvc *callsession.CallSessionService,
	roomSvc *RoomService,
	tokenSvc *TokenService,
	eventPub *mq.EventPublisher,
	sigHandler ...*wsadapter.SignalHandler,
) *CallOrchestrator {
	o := &CallOrchestrator{
		repo:           repo,
		cache:          cache,
		domainService:  domainSvc,
		roomService:    roomSvc,
		tokenService:   tokenSvc,
		eventPublisher: eventPub,
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "conflict"),
			"您正在通话中", "user already in active call", false,
		)
	}

	session, err := o.domainService.InitiateCall(req.InitiatorID, req.CallType, req.ConversationID, req.CircleID, req.InviteeIDs)
	if err != nil {
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "通话参数无效", err.Error())
	}

	session.ID = generateID()
	session.RoomID = "rtc-room-" + session.ID

	if o.roomService != nil {
		_ = o.roomService.CreateRoom(ctx, session.RoomID, session.MaxParticipants)
	}

	if err := o.repo.CreateCall(ctx, session); err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindSystem, "internal_error"),
			rterr.DefaultUserMessage, "persist call: "+err.Error(), true,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法接听", err.Error(), false,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法拒绝", err.Error(), false,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法取消", err.Error(), false,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法挂断", err.Error(), false,
		)
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
		return nil, "", rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法加入通话", err.Error(), false,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法离开通话", err.Error(), false,
		)
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
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "invalid_argument"),
			"无法邀请", err.Error(), false,
		)
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

func (o *CallOrchestrator) ListCalls(ctx context.Context, userID string, limit int, cursor string) ([]*model.CallSession, error) {
	return o.repo.ListCallsByUserID(ctx, userID, limit, cursor)
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "操作失败", err.Error())
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "操作失败", err.Error())
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "无法开始录制", err.Error())
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "无法停止录制", err.Error())
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "无法共享屏幕", err.Error())
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
		return nil, rterr.NewInvalidArgument(rterr.ModuleRTC, "无法停止共享", err.Error())
	}
	if err := o.repo.UpdateCall(ctx, session); err != nil {
		return nil, wrapSystemError(err)
	}
	_ = o.cache.SetCallState(ctx, session)
	o.publishEvent(ctx, event.ScreenShareStopped, session, userID, nil)
	return session, nil
}

func (o *CallOrchestrator) loadSession(ctx context.Context, callID string) (*model.CallSession, error) {
	cached, _ := o.cache.GetCallState(ctx, callID)
	if cached != nil {
		return cached, nil
	}
	session, err := o.repo.FindCallByID(ctx, callID)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleRTC, rterr.KindUser, "not_found"),
			"通话不存在", "call not found: "+callID, false,
		)
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
			"type":    eventType,
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
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleRTC, rterr.KindSystem, "internal_error"),
		rterr.DefaultUserMessage, err.Error(), true,
	)
}
