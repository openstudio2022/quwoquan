package model

import (
	"errors"
	"time"
)

var _ = time.Now

// ErrConversationNotFound 是「会话不存在」的领域哨兵错误。基础设施层在查询无命中时
// 必须 wrap 本哨兵，应用层据此映射结构化 not_found，而无需 import 任何存储驱动。
var (
	ErrConversationNotFound                = errors.New("conversation not found")
	ErrCircleGroupConversationAlreadyBound = errors.New("circle group conversation already bound")
	ErrMemberNotFound                      = errors.New("conversation member not found")
	ErrUserStateNotFound                   = errors.New("conversation user state not found")
)

// Conversation is the aggregate root for the chat domain.
type Conversation struct {
	ID                    string `json:"id" bson:"_id"`
	Type                  string `json:"type" bson:"type"`
	Title                 string `json:"title" bson:"title"`
	AvatarUrl             string `json:"avatarUrl" bson:"avatarUrl"`
	GroupAvatarAssetId    string `json:"groupAvatarAssetId" bson:"groupAvatarAssetId"`
	GroupAvatarVersion    int64  `json:"groupAvatarVersion" bson:"groupAvatarVersion"`
	GroupAvatarSourceHash string `json:"groupAvatarSourceHash" bson:"groupAvatarSourceHash"`
	CreatorId             string `json:"creatorId" bson:"creatorId"`
	CircleId              string `json:"circleId" bson:"circleId"`
	CircleGroupId         string `json:"circleGroupId" bson:"circleGroupId,omitempty"`
	EntityId              string `json:"entityId" bson:"entityId"`
	OriginType            string `json:"originType" bson:"originType"`
	// OriginGreetingRequestID 是升级来源的 GreetingRequest.id，只在
	// originType=greeting_reply 时有值（contracts/chat/conversation/fields.yaml）。
	// 它让「打招呼被回复而成的会话」与冷启动私信可区分，是漏斗归因的唯一依据。
	OriginGreetingRequestID    string                        `json:"originGreetingRequestId" bson:"originGreetingRequestId,omitempty"`
	OriginIntersectionSnapshot *GreetingIntersectionSnapshot `json:"originIntersectionSnapshot,omitempty" bson:"originIntersectionSnapshot,omitempty"`
	MaxSeq                     int64                         `json:"maxSeq" bson:"maxSeq"`
	MemberCount                int                           `json:"memberCount" bson:"memberCount"`
	MembersRosterRevision      int64                         `json:"membersRosterRevision" bson:"membersRosterRevision"`
	MaxGroupSize               int                           `json:"maxGroupSize" bson:"maxGroupSize"`
	ReceiptEnabled             bool                          `json:"receiptEnabled" bson:"receiptEnabled"`
	Announcement               string                        `json:"announcement" bson:"announcement"`
	AnnouncementUpdatedBy      string                        `json:"announcementUpdatedBy" bson:"announcementUpdatedBy"`
	AnnouncementUpdatedAt      *time.Time                    `json:"announcementUpdatedAt,omitempty" bson:"announcementUpdatedAt,omitempty"`
	NameEditableByAdminOnly    bool                          `json:"nameEditableByAdminOnly" bson:"nameEditableByAdminOnly"`
	LastMessageId              string                        `json:"lastMessageId" bson:"lastMessageId"`
	LastMessagePreview         string                        `json:"lastMessagePreview" bson:"lastMessagePreview"`
	LastMessageType            string                        `json:"lastMessageType" bson:"lastMessageType"`
	LastMessageTime            time.Time                     `json:"lastMessageTime" bson:"lastMessageTime"`
	MessageCount               int                           `json:"messageCount" bson:"messageCount"`
	Status                     ConversationStatus            `json:"status" bson:"status"`
	CreatedAt                  time.Time                     `json:"createdAt" bson:"createdAt"`
	UpdatedAt                  time.Time                     `json:"updatedAt" bson:"updatedAt"`
}

// GreetingIntersectionSnapshot 是 user-service 已重解析的不可变破冰依据。
// Chat 只复制和展示，不重新计算或接受客户端直接写入。
type GreetingIntersectionSnapshot struct {
	IntersectionID string    `json:"intersectionId" bson:"intersectionId"`
	EvidenceID     string    `json:"evidenceId" bson:"evidenceId"`
	SourceRef      string    `json:"sourceRef" bson:"sourceRef"`
	ObjectTypeRef  string    `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID       string    `json:"objectId" bson:"objectId"`
	PrimaryText    string    `json:"primaryText" bson:"primaryText"`
	Dimension      string    `json:"dimension,omitempty" bson:"dimension,omitempty"`
	ResolvedAt     time.Time `json:"resolvedAt" bson:"resolvedAt"`
}

// ConversationStatus is the closed lifecycle set owned by Conversation.
type ConversationStatus string

// Conversation lifecycle states（与 metadata aggregate lifecycle 单轨一致）。
const (
	ConversationStatusActive    ConversationStatus = "active"
	ConversationStatusDissolved ConversationStatus = "dissolved"
)

// ConversationMember tracks membership in a conversation (independent collection for scale).
type ConversationMember struct {
	ID               string    `json:"id" bson:"_id"`
	ConversationId   string    `json:"conversationId" bson:"conversationId"`
	UserId           string    `json:"userId" bson:"userId"`
	UserHandle       string    `json:"userHandle" bson:"userHandle"`
	DisplayName      string    `json:"displayName" bson:"displayName"`
	AvatarUrl        string    `json:"avatarUrl" bson:"avatarUrl"`
	AvatarAssetId    string    `json:"avatarAssetId" bson:"avatarAssetId"`
	AvatarVersion    int64     `json:"avatarVersion" bson:"avatarVersion"`
	MemberType       string    `json:"memberType" bson:"memberType"`
	Role             string    `json:"role" bson:"role"`
	AssistantSkillId string    `json:"assistantSkillId" bson:"assistantSkillId"`
	InvitedBy        string    `json:"invitedBy" bson:"invitedBy"`
	JoinedAt         time.Time `json:"joinedAt" bson:"joinedAt"`
}

// ConversationUserState holds per-user conversation state (readSeq, unread, mute, pin).
type ConversationUserState struct {
	ID                 string    `json:"id" bson:"_id"`
	UserId             string    `json:"userId" bson:"userId"`
	ConversationId     string    `json:"conversationId" bson:"conversationId"`
	ReadSeq            int64     `json:"readSeq" bson:"readSeq"`
	InboxProjectedSeq  int64     `json:"-" bson:"inboxProjectedSeq"`
	UnreadCount        int       `json:"unreadCount" bson:"unreadCount"`
	MentionUnreadCount int       `json:"mentionUnreadCount" bson:"mentionUnreadCount"`
	Muted              bool      `json:"muted" bson:"muted"`
	Pinned             bool      `json:"pinned" bson:"pinned"`
	LastReadAt         time.Time `json:"lastReadAt" bson:"lastReadAt"`
	UpdatedAt          time.Time `json:"updatedAt" bson:"updatedAt"`
}
