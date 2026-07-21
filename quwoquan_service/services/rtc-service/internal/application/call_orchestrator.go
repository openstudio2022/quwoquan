package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"

	"quwoquan_service/services/rtc-service/internal/application/commandmeta"
	callsession "quwoquan_service/services/rtc-service/internal/domain/call_session"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/event"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
	"quwoquan_service/services/rtc-service/internal/generated"
)

const (
	callReceiptTTL   = 24 * time.Hour
	maxCommitRetries = 3
)

// ErrVersionConflict 由 store 在 CAS 失败时返回，orchestrator 据此重放意图。
var ErrVersionConflict = errors.New("rtc: call session version conflict")

type CallOrchestrator struct {
	repo          CallStore
	cache         CallStateCache
	domainService *callsession.CallSessionService
	roomService   *RoomService
	mediaProvider MediaRoomProvider
	relationships RelationshipGate
	now           func() time.Time
}

type CallOrchestratorOption func(*CallOrchestrator)

// WithClock 注入应用层命令时钟，供超时边界、startedAt 与测试确定性共用。
func WithClock(now func() time.Time) CallOrchestratorOption {
	return func(orchestrator *CallOrchestrator) {
		if now != nil {
			orchestrator.now = now
		}
	}
}

func NewCallOrchestrator(
	repo CallStore,
	cache CallStateCache,
	domainSvc *callsession.CallSessionService,
	mediaProvider MediaRoomProvider,
	relationships RelationshipGate,
	options ...CallOrchestratorOption,
) *CallOrchestrator {
	if relationships == nil {
		relationships = DenyRelationshipGate()
	}
	var roomService *RoomService
	if mediaProvider != nil {
		roomService = NewRoomService(mediaProvider)
	}
	orchestrator := &CallOrchestrator{
		repo:          repo,
		cache:         cache,
		domainService: domainSvc,
		roomService:   roomService,
		mediaProvider: mediaProvider,
		relationships: relationships,
		now:           time.Now,
	}
	for _, option := range options {
		if option != nil {
			option(orchestrator)
		}
	}
	return orchestrator
}

type InitiateCallRequest struct {
	InitiatorID    string   `json:"initiatorId"`
	CallType       string   `json:"callType"`
	ConversationID string   `json:"conversationId"`
	CircleID       string   `json:"circleId"`
	InviteeIDs     []string `json:"inviteeIds"`
}

type InitiateCallResponse struct {
	Session     *model.CallSession `json:"session"`
	MediaAccess MediaSessionAccess `json:"mediaAccess"`
}

func (o *CallOrchestrator) InitiateCall(ctx context.Context, req InitiateCallRequest) (*InitiateCallResponse, error) {
	actorID := strings.TrimSpace(req.InitiatorID)
	if actorID == "" {
		return nil, generated.AppErrorFromUnauthorized("initiate requires an authenticated persona")
	}
	digest := commandDigest("InitiateCall", req)
	if replayed, found, err := o.replay(ctx, actorID, "InitiateCall", digest); err != nil || found {
		if found {
			return o.initiateResponse(ctx, replayed.Session, actorID)
		}
		return nil, err
	}
	if existing, _ := o.repo.FindActiveCallForUser(ctx, actorID); existing != nil {
		return nil, generated.AppErrorFromAlreadyInCall("user already in active call")
	}
	if err := o.ensureOneToOneRelationshipGate(ctx, req); err != nil {
		return nil, err
	}

	session, err := o.domainService.InitiateCall(actorID, req.CallType, req.ConversationID, req.CircleID, req.InviteeIDs)
	if err != nil {
		return nil, generated.AppErrorFromInvalidCallAction("initiate: " + err.Error())
	}
	now := o.now().UTC()
	session.ID = generateID()
	session.RoomID = "rtc-room-" + session.ID
	session.Version = 0
	session.CreatedAt = now
	session.UpdatedAt = now
	o.domainService.SetRinging(session)

	if o.roomService == nil {
		return nil, generated.AppErrorFromMediaTransportUnavailable(
			"media room provider is unavailable",
		)
	}
	if err := o.roomService.CreateRoom(ctx, session.RoomID, session.MaxParticipants); err != nil {
		return nil, generated.AppErrorFromMediaTransportUnavailable(
			"media room creation failed",
		)
	}

	ringingTargets := o.participantIDs(session, actorID, true)
	events := []CallOutboxEvent{
		o.buildEvent(
			event.CallInitiated,
			session,
			actorID,
			CallEventPayload{},
			now,
			ringingTargets,
		),
	}
	events = append(
		events,
		o.buildRingingEvents(
			session,
			actorID,
			CallEventPayload{},
			now,
			ringingTargets,
		)...,
	)
	result, err := o.commitCreate(ctx, actorID, session, "InitiateCall", digest, events, now)
	if err != nil {
		return nil, err
	}
	return o.initiateResponse(ctx, result.Session, actorID)
}

func (o *CallOrchestrator) initiateResponse(
	ctx context.Context,
	session *model.CallSession,
	actorID string,
) (*InitiateCallResponse, error) {
	mediaAccess, err := o.issueMediaAccess(ctx, session.RoomID, actorID)
	if err != nil {
		return nil, err
	}
	return &InitiateCallResponse{Session: session, MediaAccess: mediaAccess}, nil
}

type AnswerCallResponse struct {
	Session     *model.CallSession `json:"session"`
	MediaAccess MediaSessionAccess `json:"mediaAccess"`
}

func (o *CallOrchestrator) AnswerCall(ctx context.Context, callID, userID string) (*AnswerCallResponse, error) {
	result, err := o.mutate(ctx, callID, userID, "AnswerCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if err := o.domainService.AnswerCall(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromCannotAnswer(err.Error())
		}
		return event.CallAnswered, CallEventPayload{}, nil
	})
	if err != nil {
		return nil, err
	}
	mediaAccess, err := o.issueMediaAccess(ctx, result.RoomID, userID)
	if err != nil {
		return nil, err
	}
	return &AnswerCallResponse{Session: result, MediaAccess: mediaAccess}, nil
}

func (o *CallOrchestrator) RejectCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "RejectCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if session.Status == model.StatusEnded {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.RejectCall(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("reject: " + err.Error())
		}
		return event.CallEnded, CallEventPayload{EndReason: session.EndReason}, nil
	})
}

func (o *CallOrchestrator) CancelCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "CancelCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if session.Status == model.StatusEnded {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.CancelCall(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("cancel: " + err.Error())
		}
		return event.CallEnded, CallEventPayload{EndReason: session.EndReason}, nil
	})
}

func (o *CallOrchestrator) HangupCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "HangupCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if session.Status == model.StatusEnded {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.HangupCall(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("hangup: " + err.Error())
		}
		if session.Status == model.StatusEnded {
			return event.CallEnded, CallEventPayload{EndReason: session.EndReason}, nil
		}
		return event.ParticipantLeft, CallEventPayload{}, nil
	})
}

type JoinCallResponse struct {
	Session     *model.CallSession `json:"session"`
	MediaAccess MediaSessionAccess `json:"mediaAccess"`
}

func (o *CallOrchestrator) JoinCall(
	ctx context.Context,
	callID string,
	userID string,
) (*JoinCallResponse, error) {
	result, err := o.mutate(ctx, callID, userID, "JoinCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if err := o.domainService.JoinCall(session, userID); err != nil {
			if err.Error() == "call is full" {
				return "", CallEventPayload{}, generated.AppErrorFromCallFull("join: call is full")
			}
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("join: " + err.Error())
		}
		return event.ParticipantJoined, CallEventPayload{}, nil
	})
	if err != nil {
		return nil, err
	}
	mediaAccess, err := o.issueMediaAccess(ctx, result.RoomID, userID)
	if err != nil {
		return nil, err
	}
	return &JoinCallResponse{
		Session:     result,
		MediaAccess: mediaAccess,
	}, nil
}

func (o *CallOrchestrator) issueMediaAccess(
	ctx context.Context,
	roomID string,
	participantID string,
) (MediaSessionAccess, error) {
	if o.mediaProvider == nil {
		return MediaSessionAccess{}, generated.AppErrorFromMediaTransportUnavailable(
			"media access provider is unavailable",
		)
	}
	access, err := o.mediaProvider.IssueParticipantAccess(
		ctx,
		roomID,
		participantID,
	)
	if err != nil || strings.TrimSpace(access.AccessToken) == "" {
		return MediaSessionAccess{}, generated.AppErrorFromMediaTransportUnavailable(
			"media access issuance failed",
		)
	}
	return access, nil
}

func (o *CallOrchestrator) LeaveCall(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "LeaveCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if err := o.domainService.LeaveCall(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("leave: " + err.Error())
		}
		if o.roomService != nil {
			_ = o.roomService.RemoveParticipant(ctx, session.RoomID, userID)
		}
		return event.ParticipantLeft, CallEventPayload{}, nil
	})
}

// ReportMediaConnected 记录端侧媒体建连事实（首帧媒体连通后上报）。
// ≥2 人 connected 时会话进入 in_call 并记录 startedAt；已 connected 的重复
// 上报按 no-op receipt 幂等；CallConnected 事件推送全部参与者。
func (o *CallOrchestrator) ReportMediaConnected(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "ReportMediaConnected", func(session *model.CallSession) (string, CallEventPayload, error) {
		if p := participantOf(session, userID); p != nil && p.Status == model.ParticipantConnected {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.SetConnected(session, userID, o.now().UTC()); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("report connected: " + err.Error())
		}
		return event.CallConnected, CallEventPayload{}, nil
	})
}

func (o *CallOrchestrator) InviteToCall(ctx context.Context, callID, userID string, inviteeIDs []string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "InviteToCall", func(session *model.CallSession) (string, CallEventPayload, error) {
		if err := o.domainService.InviteToCall(session, inviteeIDs); err != nil {
			if err.Error() == "exceeds max participants" {
				return "", CallEventPayload{}, generated.AppErrorFromCallFull("invite: exceeds max participants")
			}
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("invite: " + err.Error())
		}
		return event.CallRinging, CallEventPayload{InviteeIDs: inviteeIDs}, nil
	})
}

func (o *CallOrchestrator) GetCall(
	ctx context.Context,
	callID string,
	userID string,
) (*model.CallSession, error) {
	session, err := o.loadSession(ctx, callID)
	if err != nil {
		return nil, err
	}
	if participantOf(session, strings.TrimSpace(userID)) == nil {
		return nil, generated.AppErrorFromNotParticipant(
			"actor is not a call participant",
		)
	}
	return session, nil
}

// ListCallsFilter 表达通话记录列表的筛选条件（与 service.yaml ListCalls query_params 对齐）。
type ListCallsFilter struct {
	Status     string
	MissedOnly bool
}

func (o *CallOrchestrator) ListCalls(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
	filter ListCallsFilter,
) (CallHistoryPage, error) {
	return o.repo.ListCallsByUserID(ctx, userID, CallHistoryQuery{
		Limit:      limit,
		Cursor:     cursor,
		Status:     strings.TrimSpace(filter.Status),
		MissedOnly: filter.MissedOnly,
	})
}

type ToggleMuteRequest struct {
	Muted bool `json:"muted"`
}

func (o *CallOrchestrator) ToggleMute(ctx context.Context, callID, userID string, muted bool) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "ToggleMute", func(session *model.CallSession) (string, CallEventPayload, error) {
		if p := participantOf(session, userID); p != nil && p.IsMuted == muted {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.ToggleMute(session, userID, muted); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("toggle mute: " + err.Error())
		}
		return "", CallEventPayload{}, nil
	})
}

type ToggleCameraRequest struct {
	CameraOn bool `json:"cameraOn"`
}

func (o *CallOrchestrator) ToggleCamera(ctx context.Context, callID, userID string, cameraOn bool) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "ToggleCamera", func(session *model.CallSession) (string, CallEventPayload, error) {
		if p := participantOf(session, userID); p != nil && p.IsCameraOn == cameraOn {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.ToggleCamera(session, userID, cameraOn); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromInvalidCallAction("toggle camera: " + err.Error())
		}
		return "", CallEventPayload{}, nil
	})
}

func (o *CallOrchestrator) StartScreenShare(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "StartScreenShare", func(session *model.CallSession) (string, CallEventPayload, error) {
		if session.IsScreenSharing && session.ScreenShareUserID == userID {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.StartScreenShare(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromScreenShareConflict("start screen share: " + err.Error())
		}
		return event.ScreenShareStarted, CallEventPayload{}, nil
	})
}

func (o *CallOrchestrator) StopScreenShare(ctx context.Context, callID, userID string) (*model.CallSession, error) {
	return o.mutate(ctx, callID, userID, "StopScreenShare", func(session *model.CallSession) (string, CallEventPayload, error) {
		if !session.IsScreenSharing {
			return "", CallEventPayload{}, errNoop
		}
		if err := o.domainService.StopScreenShare(session, userID); err != nil {
			return "", CallEventPayload{}, generated.AppErrorFromScreenShareConflict("stop screen share: " + err.Error())
		}
		return event.ScreenShareStopped, CallEventPayload{}, nil
	})
}

// errNoop 表示命名意图的目标状态已满足：写 no-op receipt，不改状态、不发事件。
var errNoop = errors.New("rtc: command is a no-op")

// applyFunc 在已加载的最新聚合上执行领域意图，返回要发布的事件类型与载荷。
// 返回 eventType == "" 表示状态改变但无实时事件；返回 errNoop 表示无需改变。
type applyFunc func(session *model.CallSession) (string, CallEventPayload, error)

type mutationCommand struct {
	actorID            string
	idempotencyKey     string
	commandName        string
	digest             string
	requireParticipant bool
}

type mutationOutcome struct {
	Session *model.CallSession
	Changed bool
}

func (o *CallOrchestrator) mutate(
	ctx context.Context,
	callID string,
	userID string,
	commandName string,
	apply applyFunc,
) (*model.CallSession, error) {
	actorID := strings.TrimSpace(userID)
	if actorID == "" {
		return nil, generated.AppErrorFromUnauthorized(commandName + " requires an authenticated persona")
	}
	digest := commandDigest(commandName, callID)
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return nil, err
	}
	outcome, err := o.mutateCommand(ctx, callID, mutationCommand{
		actorID:            actorID,
		idempotencyKey:     key,
		commandName:        commandName,
		digest:             digest,
		requireParticipant: true,
	}, apply)
	if err != nil {
		return nil, err
	}
	return outcome.Session, nil
}

// mutateCommand 是用户命令与系统命令共享的唯一写入管道：
// receipt replay → authoritative load → aggregate behavior → CAS/receipt/outbox commit。
func (o *CallOrchestrator) mutateCommand(
	ctx context.Context,
	callID string,
	command mutationCommand,
	apply applyFunc,
) (mutationOutcome, error) {
	if replayed, found, err := o.replayWithKey(
		ctx,
		command.idempotencyKey,
		command.commandName,
		command.digest,
	); err != nil || found {
		if found {
			return mutationOutcome{Session: replayed.Session}, nil
		}
		return mutationOutcome{}, err
	}
	for attempt := 0; attempt < maxCommitRetries; attempt++ {
		session, err := o.repo.FindCallByID(ctx, callID)
		if err != nil || session == nil {
			return mutationOutcome{}, generated.AppErrorFromCallNotFound("call not found: " + callID)
		}
		if command.requireParticipant &&
			participantOf(session, command.actorID) == nil &&
			session.InitiatorID != command.actorID {
			return mutationOutcome{}, generated.AppErrorFromNotParticipant("actor is not a call participant")
		}
		expectedVersion := session.Version
		now := o.now().UTC()
		eventType, payload, applyErr := apply(session)
		if errors.Is(applyErr, errNoop) {
			result, recordErr := o.recordNoopWithKey(
				ctx,
				command.idempotencyKey,
				session,
				command.commandName,
				command.digest,
			)
			return mutationOutcome{Session: result}, recordErr
		}
		if applyErr != nil {
			return mutationOutcome{}, applyErr
		}
		session.UpdatedAt = now
		var events []CallOutboxEvent
		if eventType != "" {
			payload.Status = session.Status
			payload.ParticipantCount = session.ParticipantCount
			recipients := o.participantIDs(
				session,
				command.actorID,
				eventType == event.CallRinging,
			)
			if eventType == event.CallRinging {
				if len(payload.InviteeIDs) > 0 {
					recipients = payload.InviteeIDs
				}
				events = append(
					events,
					o.buildRingingEvents(
						session,
						command.actorID,
						payload,
						now,
						recipients,
					)...,
				)
			} else {
				events = append(events, o.buildEvent(
					eventType,
					session,
					command.actorID,
					payload,
					now,
					recipients,
				))
			}
		}
		result, commitErr := o.commitWithKey(
			ctx,
			command.idempotencyKey,
			session,
			expectedVersion,
			command.commandName,
			command.digest,
			events,
			now,
		)
		if commitErr == nil {
			o.cleanupIfEnded(ctx, result.Session)
			return mutationOutcome{
				Session: result.Session,
				Changed: !result.Replayed,
			}, nil
		}
		if !errors.Is(commitErr, ErrVersionConflict) || attempt == maxCommitRetries-1 {
			if errors.Is(commitErr, ErrVersionConflict) {
				return mutationOutcome{}, generated.AppErrorFromInternalError(
					"call changed repeatedly while applying " + command.commandName,
				)
			}
			return mutationOutcome{}, commitErr
		}
	}
	panic("unreachable rtc mutate retry")
}

func (o *CallOrchestrator) commitCreate(
	ctx context.Context,
	actorID string,
	session *model.CallSession,
	commandName string,
	digest string,
	events []CallOutboxEvent,
	now time.Time,
) (CallCommitResult, error) {
	return o.commit(ctx, actorID, session, 0, commandName, digest, events, now)
}

func (o *CallOrchestrator) commit(
	ctx context.Context,
	actorID string,
	session *model.CallSession,
	expectedVersion int64,
	commandName string,
	digest string,
	events []CallOutboxEvent,
	now time.Time,
) (CallCommitResult, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CallCommitResult{}, err
	}
	return o.commitWithKey(
		ctx,
		key,
		session,
		expectedVersion,
		commandName,
		digest,
		events,
		now,
	)
}

func (o *CallOrchestrator) commitWithKey(
	ctx context.Context,
	idempotencyKey string,
	session *model.CallSession,
	expectedVersion int64,
	commandName string,
	digest string,
	events []CallOutboxEvent,
	now time.Time,
) (CallCommitResult, error) {
	result, err := o.repo.Commit(ctx, CallCommit{
		Session:          session,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: now.Add(callReceiptTTL),
		Events:           events,
	})
	if err != nil {
		return CallCommitResult{}, err
	}
	_ = o.cache.SetCallState(ctx, result.Session)
	return result, nil
}

func (o *CallOrchestrator) recordNoopWithKey(
	ctx context.Context,
	idempotencyKey string,
	session *model.CallSession,
	commandName string,
	digest string,
) (*model.CallSession, error) {
	result, err := o.repo.RecordNoopReceipt(ctx, CallNoopReceipt{
		Session:          session,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    digest,
		ReceiptExpiresAt: o.now().UTC().Add(callReceiptTTL),
	})
	if err != nil {
		return nil, err
	}
	return result.Session, nil
}

func (o *CallOrchestrator) replay(
	ctx context.Context,
	actorID string,
	commandName string,
	digest string,
) (CallCommitResult, bool, error) {
	key, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CallCommitResult{}, false, err
	}
	return o.replayWithKey(ctx, key, commandName, digest)
}

func (o *CallOrchestrator) replayWithKey(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	digest string,
) (CallCommitResult, bool, error) {
	return o.repo.FindReceipt(ctx, idempotencyKey, commandName, digest)
}

func (o *CallOrchestrator) buildEvent(
	eventType string,
	session *model.CallSession,
	actorID string,
	payload CallEventPayload,
	now time.Time,
	recipients []string,
) CallOutboxEvent {
	targetPersonaID := ""
	if eventType == event.CallRinging && len(recipients) == 1 {
		targetPersonaID = strings.TrimSpace(recipients[0])
	}
	aggregateVersion := session.Version + 1
	eventID := eventIdentifier(
		session.ID,
		eventType,
		aggregateVersion,
		targetPersonaID,
	)
	payload.CallID = session.ID
	payload.EventID = eventID
	payload.CallType = session.CallType
	payload.InitiatorID = session.InitiatorID
	payload.InitiatorRingtoneID = session.InitiatorRingtoneID
	payload.ConversationID = session.ConversationID
	payload.CircleID = session.CircleID
	payload.MaxParticipants = session.MaxParticipants
	payload.UserID = actorID
	payload.Status = session.Status
	payload.ParticipantCount = session.ParticipantCount
	payload.EndReason = session.EndReason
	payload.DurationMs = session.DurationMs
	if session.StartedAt != nil {
		payload.StartedAt = session.StartedAt.UTC().Format(time.RFC3339Nano)
	}
	if session.EndedAt != nil {
		payload.EndedAt = session.EndedAt.UTC().Format(time.RFC3339Nano)
	}
	if eventType == event.CallRinging {
		payload.TargetPersonaID = targetPersonaID
		payload.CallerName = actorID
		payload.CallerAvatarURL = ""
		payload.SourceLabel = callSourceLabel(session)
		payload.TrustRelation = callTrustRelation(session)
		payload.DeliveryKey = incomingCallDeliveryKey(
			session.ID,
			targetPersonaID,
		)
		payload.ExpiresAt = now.Add(
			callRingingTTL(session),
		).UTC().Format(time.RFC3339Nano)
	}
	if participant := participantOf(session, actorID); participant != nil {
		payload.Role = participant.Role
	}
	// wire type（call.ringing 等）与 events.yaml client_ws_type 同源，
	// 是客户端消费契约；领域事件名只作为 outbox EventType 存档。
	body, _ := json.Marshal(callEventBody{
		Type:       signalWireType(eventType),
		CallID:     session.ID,
		ActorID:    actorID,
		Payload:    payload,
		Recipients: recipients,
		Timestamp:  now,
	})
	return CallOutboxEvent{
		EventID:          eventID,
		EventType:        eventType,
		AggregateID:      session.ID,
		AggregateVersion: aggregateVersion,
		DeliveryKey:      payload.DeliveryKey,
		Payload:          body,
		OccurredAt:       now,
	}
}

func (o *CallOrchestrator) buildRingingEvents(
	session *model.CallSession,
	actorID string,
	payload CallEventPayload,
	now time.Time,
	targets []string,
) []CallOutboxEvent {
	seen := make(map[string]struct{}, len(targets))
	events := make([]CallOutboxEvent, 0, len(targets))
	for _, target := range targets {
		target = strings.TrimSpace(target)
		if target == "" || target == actorID {
			continue
		}
		if _, exists := seen[target]; exists {
			continue
		}
		seen[target] = struct{}{}
		events = append(
			events,
			o.buildEvent(
				event.CallRinging,
				session,
				actorID,
				payload,
				now,
				[]string{target},
			),
		)
	}
	return events
}

type callEventBody struct {
	Type       string           `json:"type"`
	CallID     string           `json:"callId"`
	ActorID    string           `json:"actorId,omitempty"`
	Payload    CallEventPayload `json:"payload"`
	Recipients []string         `json:"recipients"`
	Timestamp  time.Time        `json:"timestamp"`
}

func decodeRecipients(evt CallOutboxEvent) []string {
	var body callEventBody
	if err := json.Unmarshal(evt.Payload, &body); err != nil {
		return nil
	}
	return body.Recipients
}

// participantIDs 返回事件接收者。ringing 只推给发起者以外的被邀人（来电提示），
// 其余事件推给全部参与者。
func (o *CallOrchestrator) participantIDs(session *model.CallSession, actorID string, ringingOnly bool) []string {
	ids := make([]string, 0, len(session.Participants))
	for _, p := range session.Participants {
		if ringingOnly && p.UserID == actorID {
			continue
		}
		ids = append(ids, p.UserID)
	}
	return ids
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
	if err != nil || session == nil {
		return nil, generated.AppErrorFromCallNotFound("call not found: " + callID)
	}
	_ = o.cache.SetCallState(ctx, session)
	return session, nil
}

func (o *CallOrchestrator) cleanupIfEnded(ctx context.Context, session *model.CallSession) {
	if session.Status != model.StatusEnded {
		return
	}
	if o.roomService != nil {
		_ = o.roomService.DeleteRoom(ctx, session.RoomID)
	}
}

func participantOf(session *model.CallSession, userID string) *model.Participant {
	for i := range session.Participants {
		if session.Participants[i].UserID == userID {
			return &session.Participants[i]
		}
	}
	return nil
}

func commandDigest(commandName string, payload any) string {
	body, _ := json.Marshal(payload)
	sum := sha256.Sum256(append([]byte(commandName+"\x00"), body...))
	return hex.EncodeToString(sum[:])
}

func scopedIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	raw := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if raw == "" {
		return "", generated.AppErrorFromInternalError("call command requires Idempotency-Key")
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + raw))
	return "rtc-call:" + hex.EncodeToString(sum[:]), nil
}

func eventIdentifier(
	callID string,
	eventType string,
	version int64,
	targetPersonaID string,
) string {
	sum := sha256.Sum256([]byte(
		callID + "\x00" +
			eventType + "\x00" +
			strconv.FormatInt(version, 10) + "\x00" +
			strings.TrimSpace(targetPersonaID),
	))
	return "rtc-evt-" + hex.EncodeToString(sum[:16])
}

func incomingCallDeliveryKey(callID string, targetPersonaID string) string {
	sum := sha256.Sum256([]byte(
		strings.TrimSpace(callID) + "\x00" +
			strings.TrimSpace(targetPersonaID),
	))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func callRingingTTL(session *model.CallSession) time.Duration {
	if session != nil &&
		session.MaxParticipants > model.MaxParticipants1v1 {
		return 60 * time.Second
	}
	return 30 * time.Second
}

func callSourceLabel(session *model.CallSession) string {
	if session == nil {
		return "direct_call"
	}
	if strings.TrimSpace(session.CircleID) != "" {
		return "circle"
	}
	if strings.TrimSpace(session.ConversationID) != "" {
		return "conversation"
	}
	return "direct_call"
}

func callTrustRelation(session *model.CallSession) string {
	if session != nil &&
		session.MaxParticipants <= model.MaxParticipants1v1 {
		return "known"
	}
	return "possibly_unknown"
}
