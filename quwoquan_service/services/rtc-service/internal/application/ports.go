package application

import (
	"context"
	"time"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

// CallOutboxEvent 是与聚合状态在同一事务提交的不可变事实。
type CallOutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	DeliveryKey      string
	Payload          []byte
	OccurredAt       time.Time
}

// CallCommit 声明一次聚合写入的原子提交单元：state（version CAS）、
// 幂等 receipt 与同库 outbox 在同一事务落盘。
type CallCommit struct {
	Session          *model.CallSession
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []CallOutboxEvent
}

// CallCommitResult 是提交或幂等重放的结果。
type CallCommitResult struct {
	Session  *model.CallSession
	Replayed bool
}

// CallHistoryQuery 是 CallHistoryReader 的强类型查询，筛选与分页均在权威存储执行。
type CallHistoryQuery struct {
	Limit      int
	Cursor     string
	Status     string
	MissedOnly bool
}

// CallHistoryPage 是 ListCalls 返回的 typed Slice。
type CallHistoryPage struct {
	Items      []*model.CallSession `json:"items"`
	NextCursor string               `json:"nextCursor"`
}

// CallStore 是通话聚合的对象专属持久化端口：Load + 原子 Commit + 具名 Reader。
type CallStore interface {
	CreateCall(ctx context.Context, session *model.CallSession) error
	FindCallByID(ctx context.Context, id string) (*model.CallSession, error)
	FindActiveCallForUser(ctx context.Context, userID string) (*model.CallSession, error)
	// FindOverdueRingingCalls 按 1v1/群聊各自 cutoff 返回到期振铃会话；
	// 领域 HandleTimeout 在命令管道内再次校验状态与精确边界。
	FindOverdueRingingCalls(
		ctx context.Context,
		oneToOneCutoff time.Time,
		groupCutoff time.Time,
		limit int,
	) ([]*model.CallSession, error)
	Commit(ctx context.Context, commit CallCommit) (CallCommitResult, error)
	FindReceipt(ctx context.Context, idempotencyKey, commandName, commandDigest string) (CallCommitResult, bool, error)
	RecordNoopReceipt(ctx context.Context, receipt CallNoopReceipt) (CallCommitResult, error)
	ListCallsByUserID(ctx context.Context, userID string, query CallHistoryQuery) (CallHistoryPage, error)
}

type CallOutboxStore interface {
	ReadPendingOutbox(ctx context.Context, limit int) ([]CallOutboxEvent, error)
	MarkOutboxPublished(ctx context.Context, eventID string, publishedAt time.Time) error
}

// CallNoopReceipt 记录目标状态已满足的命名意图：写幂等 receipt 但不递增
// version、不产生 outbox 事实。
type CallNoopReceipt struct {
	Session          *model.CallSession
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

// CallStateCache 是通话编排所需的短期状态缓存端口（storage.yaml redis_cache 同源）。
// already_in_call 冲突检测走 Mongo FindActiveCallForUser，振铃超时走进程内
// sweeper（lifecycle_timers.ring_timeout）；不存在 Redis active_call/timeout key。
type CallStateCache interface {
	SetCallState(ctx context.Context, session *model.CallSession) error
	GetCallState(ctx context.Context, callID string) (*model.CallSession, error)
}

// RoomParticipant 是应用层可消费的房间参与者快照。
type RoomParticipant struct {
	Identity string
	SID      string
	State    string
}

// MediaSessionAccess 是参与者加入媒体房间所需的供应商中立访问材料。
// 它只表达当前会话的连接能力，不承载 Adapter ID、凭据配置或供应商错误。
type MediaSessionAccess struct {
	AccessToken string `json:"accessToken"`
}

// MediaRoomProvider 隔离应用层与具体 RTC 房间供应商。
type MediaRoomProvider interface {
	CreateRoom(ctx context.Context, roomName string, maxParticipants int) error
	DeleteRoom(ctx context.Context, roomName string) error
	ListParticipants(ctx context.Context, roomName string) ([]RoomParticipant, error)
	RemoveParticipant(ctx context.Context, roomName string, identity string) error
	IssueParticipantAccess(
		ctx context.Context,
		roomName string,
		participantIdentity string,
	) (MediaSessionAccess, error)
}

// CallEventPayload 是事件与实时信令共享的强类型载荷。
type CallEventPayload struct {
	CallID              string   `json:"callId"`
	EventID             string   `json:"eventId,omitempty"`
	CallType            string   `json:"callType,omitempty"`
	InitiatorID         string   `json:"initiatorId,omitempty"`
	InitiatorRingtoneID string   `json:"initiatorRingtoneId,omitempty"`
	TargetPersonaID     string   `json:"targetPersonaId,omitempty"`
	CallerName          string   `json:"callerName,omitempty"`
	CallerAvatarURL     string   `json:"callerAvatarUrl"`
	SourceLabel         string   `json:"sourceLabel,omitempty"`
	TrustRelation       string   `json:"trustRelation,omitempty"`
	DeliveryKey         string   `json:"deliveryKey,omitempty"`
	ConversationID      string   `json:"conversationId,omitempty"`
	CircleID            string   `json:"circleId,omitempty"`
	MaxParticipants     int      `json:"maxParticipants,omitempty"`
	UserID              string   `json:"userId,omitempty"`
	Role                string   `json:"role,omitempty"`
	Status              string   `json:"status"`
	ParticipantCount    int      `json:"participantCount"`
	EndReason           string   `json:"endReason,omitempty"`
	DurationMs          int64    `json:"durationMs,omitempty"`
	StartedAt           string   `json:"startedAt,omitempty"`
	EndedAt             string   `json:"endedAt,omitempty"`
	ExpiresAt           string   `json:"expiresAt,omitempty"`
	InviteeIDs          []string `json:"inviteeIds,omitempty"`
}

// CallRealtimePublisher 是 CallSession outbox 的唯一 relay adapter。
// CallRinging 只追加 durable stream；其余在线信令按可信 persona 通道发布，
// CallAnswered/CallEnded 还必须追加 durable cancellation stream。
type CallRealtimePublisher interface {
	PublishToPersonas(ctx context.Context, personaIDs []string, wireType string, event CallOutboxEvent) error
}
