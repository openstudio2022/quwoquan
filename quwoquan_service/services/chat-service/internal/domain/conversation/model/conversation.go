package model

import (
	"errors"
	"time"
)

var _ = time.Now

// ErrConversationNotFound 是「会话不存在」的领域哨兵错误。基础设施层在查询无命中时
// 必须 wrap 本哨兵，应用层据此映射结构化 not_found，而无需 import 任何存储驱动。
var (
	ErrConversationNotFound = errors.New("conversation not found")
	ErrMemberNotFound       = errors.New("conversation member not found")
)

// Conversation is the aggregate root for the chat domain.
type Conversation struct {
	ID                    string    `json:"id" bson:"_id"`
	Type                  string    `json:"type" bson:"type"`
	Title                 string    `json:"title" bson:"title"`
	AvatarUrl             string    `json:"avatarUrl" bson:"avatarUrl"`
	GroupAvatarAssetId    string    `json:"groupAvatarAssetId" bson:"groupAvatarAssetId"`
	GroupAvatarVersion    int64     `json:"groupAvatarVersion" bson:"groupAvatarVersion"`
	GroupAvatarSourceHash string    `json:"groupAvatarSourceHash" bson:"groupAvatarSourceHash"`
	CreatorId             string    `json:"creatorId" bson:"creatorId"`
	CircleId              string    `json:"circleId" bson:"circleId"`
	CircleGroupId         string    `json:"circleGroupId" bson:"circleGroupId"`
	EntityId              string    `json:"entityId" bson:"entityId"`
	OriginType            string    `json:"originType" bson:"originType"`
	BindingType           string    `json:"bindingType" bson:"bindingType"`
	LifecyclePolicy       string    `json:"lifecyclePolicy" bson:"lifecyclePolicy"`
	MaxSeq                int64     `json:"maxSeq" bson:"maxSeq"`
	MemberCount           int       `json:"memberCount" bson:"memberCount"`
	MembersRosterRevision int64     `json:"membersRosterRevision" bson:"membersRosterRevision"`
	MaxGroupSize          int       `json:"maxGroupSize" bson:"maxGroupSize"`
	ReceiptEnabled        bool      `json:"receiptEnabled" bson:"receiptEnabled"`
	LastMessageId         string    `json:"lastMessageId" bson:"lastMessageId"`
	LastMessagePreview    string    `json:"lastMessagePreview" bson:"lastMessagePreview"`
	LastMessageTime       time.Time `json:"lastMessageTime" bson:"lastMessageTime"`
	MessageCount          int       `json:"messageCount" bson:"messageCount"`
	Status                string    `json:"status" bson:"status"`
	CreatedAt             time.Time `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time `json:"updatedAt" bson:"updatedAt"`
}

// ConversationMember tracks membership in a conversation (independent collection for scale).
type ConversationMember struct {
	ID               string    `json:"id" bson:"_id"`
	ConversationId   string    `json:"conversationId" bson:"conversationId"`
	UserId           string    `json:"userId" bson:"userId"`
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
	UnreadCount        int       `json:"unreadCount" bson:"unreadCount"`
	MentionUnreadCount int       `json:"mentionUnreadCount" bson:"mentionUnreadCount"`
	Muted              bool      `json:"muted" bson:"muted"`
	Pinned             bool      `json:"pinned" bson:"pinned"`
	LastReadAt         time.Time `json:"lastReadAt" bson:"lastReadAt"`
	UpdatedAt          time.Time `json:"updatedAt" bson:"updatedAt"`
}
