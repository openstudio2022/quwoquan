package application

import (
	"context"
	"time"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

// CallStore 是通话用例所需的最小聚合持久化端口。
type CallStore interface {
	CreateCall(ctx context.Context, session *model.CallSession) error
	FindCallByID(ctx context.Context, id string) (*model.CallSession, error)
	UpdateCall(ctx context.Context, session *model.CallSession) error
	ListCallsByUserID(ctx context.Context, userID string, limit int, cursor string) ([]*model.CallSession, error)
}

// CallStateCache 是通话编排所需的短期状态缓存端口。
type CallStateCache interface {
	SetCallState(ctx context.Context, session *model.CallSession) error
	GetCallState(ctx context.Context, callID string) (*model.CallSession, error)
	SetActiveCallForUser(ctx context.Context, userID, callID string) error
	GetActiveCallForUser(ctx context.Context, userID string) (string, error)
	DeleteActiveCallForUser(ctx context.Context, userID string) error
	SetCallTimeout(ctx context.Context, callID string, timeout time.Duration) error
	DeleteCallTimeout(ctx context.Context, callID string) error
}

// RoomParticipant 是应用层可消费的房间参与者快照。
type RoomParticipant struct {
	Identity string
	SID      string
	State    string
}

// RoomManager 隔离应用层与具体 RTC 房间供应商。
type RoomManager interface {
	CreateRoom(ctx context.Context, roomName string, maxParticipants int) error
	DeleteRoom(ctx context.Context, roomName string) error
	ListParticipants(ctx context.Context, roomName string) ([]RoomParticipant, error)
	RemoveParticipant(ctx context.Context, roomName string, identity string) error
	StartRoomCompositeEgress(ctx context.Context, roomName, outputBucket string) (string, error)
	StopEgress(ctx context.Context, egressID string) error
}

// CallTokenIssuer 为参与者签发加入房间所需的短期令牌。
type CallTokenIssuer interface {
	GenerateParticipantToken(roomName, participantIdentity string) (string, error)
}

// CallEventPayload 是事件与实时信令共享的强类型载荷。
type CallEventPayload struct {
	Status           string   `json:"status"`
	ParticipantCount int      `json:"participantCount"`
	Reason           string   `json:"reason,omitempty"`
	InviteeIDs       []string `json:"inviteeIds,omitempty"`
}

// CallEvent 是发布到跨服务事件通道的应用 DTO。
type CallEvent struct {
	Type      string           `json:"type"`
	CallID    string           `json:"callId"`
	ActorID   string           `json:"actorId,omitempty"`
	Timestamp time.Time        `json:"timestamp"`
	Payload   CallEventPayload `json:"payload"`
}

// CallEventPublisher 隔离编排用例与消息基础设施。
type CallEventPublisher interface {
	Publish(ctx context.Context, event CallEvent) error
}

// CallSignal 是发送给在线客户端的实时信令 DTO。
type CallSignal struct {
	Type    string           `json:"type"`
	CallID  string           `json:"callId"`
	ActorID string           `json:"actorId"`
	Payload CallEventPayload `json:"payload"`
}

// CallSignaler 隔离编排用例与 WebSocket 连接实现。
type CallSignaler interface {
	PushToUser(ctx context.Context, userID string, signal CallSignal)
	PushToUsers(ctx context.Context, userIDs []string, signal CallSignal)
}
