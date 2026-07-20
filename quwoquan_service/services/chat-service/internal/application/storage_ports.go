package application

import (
	"context"
	"strings"
	"time"

	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
	conversationmodel "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

// TransactionRunner 定义应用用例所需的事务边界。
type TransactionRunner interface {
	RunInTransaction(ctx context.Context, fn func(context.Context) error) error
}

// ConversationStore 仅暴露会话聚合的持久化能力。
type ConversationStore interface {
	CreateConversation(ctx context.Context, conversation *conversationmodel.Conversation) error
	FindConversationByID(ctx context.Context, id string) (*conversationmodel.Conversation, error)
	UpdateConversation(ctx context.Context, id string, conversation *conversationmodel.Conversation) error
	ListConversationsByUser(ctx context.Context, userID string, limit int, cursor string) ([]conversationmodel.Conversation, error)
	FindDirectConversationBetween(ctx context.Context, memberA, memberB string) (*conversationmodel.Conversation, error)
	ListGroupConversationsNeedingAvatar(ctx context.Context, limit int) ([]conversationmodel.Conversation, error)
}

// MessageStore 仅暴露消息聚合的持久化能力。
type MessageStore interface {
	CommitMessage(ctx context.Context, commit MessageCommit) (MessageCommitResult, error)
	FindMessageByID(ctx context.Context, id string) (*messagemodel.Message, error)
	ListMessages(ctx context.Context, conversationID string, limit int, afterSeq, beforeSeq int64) ([]messagemodel.Message, error)
	CountUnreadMessages(ctx context.Context, conversationID, userID string, afterSeq, throughSeq int64) (UnreadMessageCounts, error)
	SetMessageRecalled(ctx context.Context, id string) error
	// AppendMessageOutboxEvent 供 Recall 等已提交消息上的命名迁移在事务内
	// 追加事件；(aggregateId, aggregateVersion, eventType) 唯一索引保证重放幂等。
	AppendMessageOutboxEvent(
		ctx context.Context,
		event MessageOutboxEvent,
		aggregateID string,
		aggregateVersion int64,
	) error
}

type UnreadMessageCounts struct {
	Total     int
	Mentioned int
}

type MessageOutboxEvent struct {
	EventID        string
	EventType      string
	ConversationID string
	ActorID        string
	Payload        map[string]any
	Status         string
	Checkpoint     string
}

type MessageOutboxReader interface {
	ReadMessageOutboxAfter(ctx context.Context, checkpoint string, limit int) ([]MessageOutboxEvent, error)
}

type MessageOutboxDispatchStore interface {
	MarkMessageOutboxDispatched(ctx context.Context, eventID string, dispatchedAt time.Time) error
}

type MessageOutboxCheckpointStore interface {
	LoadMessageOutboxCheckpoint(ctx context.Context, consumer string) (string, error)
	SaveMessageOutboxCheckpoint(ctx context.Context, consumer, checkpoint string) error
}

type MessageCommit struct {
	Message       messagemodel.Message
	CommandDigest string
	Events        []MessageOutboxEvent
}

type MessageCommitResult struct {
	Message  messagemodel.Message
	Events   []MessageOutboxEvent
	Replayed bool
}

// ConversationMessageProjector 只维护可由 Message 事件重建的 Conversation
// 摘要，不暴露 Conversation 聚合写入口。
type ConversationMessageProjector interface {
	ProjectCommittedMessage(ctx context.Context, message messagemodel.Message) error
}

type MemberListSort string

const (
	MemberListSortJoinedAsc      MemberListSort = "joined_asc"
	MemberListSortDisplayNameAsc MemberListSort = "display_name_asc"
)

func NormalizeMemberListSort(raw string) MemberListSort {
	if strings.TrimSpace(raw) == string(MemberListSortDisplayNameAsc) {
		return MemberListSortDisplayNameAsc
	}
	return MemberListSortJoinedAsc
}

type ListMembersQuery struct {
	Limit  int
	Cursor string
	Role   string
	Query  string
	Sort   MemberListSort
}

// MemberStore 仅暴露成员名册所需能力，查询参数不携带存储驱动类型。
type MemberStore interface {
	CreateMember(ctx context.Context, member *conversationmodel.ConversationMember) error
	DeleteMember(ctx context.Context, conversationID, userID string) error
	FindMember(ctx context.Context, conversationID, userID string) (*conversationmodel.ConversationMember, error)
	UpdateMemberAvatarSnapshot(
		ctx context.Context,
		conversationID string,
		userID string,
		avatarURL string,
		avatarAssetID string,
		avatarVersion int64,
	) error
	UpdateMemberRole(ctx context.Context, conversationID, userID, role string) error
	ListMembers(ctx context.Context, conversationID string, query ListMembersQuery) ([]conversationmodel.ConversationMember, error)
	BumpMembersRosterRevision(ctx context.Context, conversationID string, memberCount *int) error
	CountMembers(ctx context.Context, conversationID string) (int, error)
	CountUserMembers(ctx context.Context, conversationID string) (int, error)
	FindAssistantMember(ctx context.Context, conversationID string) (*conversationmodel.ConversationMember, error)
}

type UserStateStore interface {
	UpsertUserState(ctx context.Context, state *conversationmodel.ConversationUserState) error
	FindUserState(ctx context.Context, userID, conversationID string) (*conversationmodel.ConversationUserState, error)
	ListUserStates(ctx context.Context, userID string, limit int, cursor string) ([]conversationmodel.ConversationUserState, error)
	// AdvanceInboxUnread 是 ChatInbox 投影的单调幂等写入口；eventSeq 不高于
	// inboxProjectedSeq 时为 no-op，且 eventSeq 不高于 readSeq 时只推进投影水位。
	AdvanceInboxUnread(
		ctx context.Context,
		userID string,
		conversationID string,
		eventSeq int64,
		unreadDelta int,
		mentionDelta int,
		lastMessageAt time.Time,
	) error
}

type ReceiptStore interface {
	CreateReceipt(ctx context.Context, receipt *messagemodel.MessageReceipt) error
	ListReceiptsByMessage(ctx context.Context, messageID string) ([]messagemodel.MessageReceipt, error)
}

// ConversationCache 只承载可丢弃的 Conversation 查询缓存；消息序号和幂等
// 都属于 Message 聚合的 Mongo 事务状态，不得由 Redis 充当真相源。
type ConversationCache interface {
	InvalidateConversation(ctx context.Context, conversationID string) error
}

// ChatStoragePorts 聚合细粒度端口，本身不提供转发方法或通用仓储语义。
type ChatStoragePorts struct {
	Transactions      TransactionRunner
	Conversations     ConversationStore
	Messages          MessageStore
	MessageProjection ConversationMessageProjector
	Members           MemberStore
	UserStates        UserStateStore
	Receipts          ReceiptStore
	// 三个非 Message 聚合各自的命令回执 + 事务 outbox 端口；state 写入与
	// CommitAggregateCommand 必须在同一事务闭包内完成。
	ConversationCommands AggregateCommandStore
	MembershipCommands   AggregateCommandStore
	UserStateCommands    AggregateCommandStore
}
