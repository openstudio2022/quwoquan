package model

import (
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"time"
)

var ErrNotFound = errors.New("conversation member not found")

type Member struct {
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
	InvitedBy        string    `json:"invitedBy" bson:"invitedBy"`
	JoinedAt         time.Time `json:"joinedAt" bson:"joinedAt"`
}

func (member Member) Validate() error {
	if strings.TrimSpace(member.ID) == "" ||
		strings.TrimSpace(member.ConversationId) == "" ||
		strings.TrimSpace(member.UserId) == "" ||
		member.JoinedAt.IsZero() {
		return errors.New("conversation membership identity and joinedAt are required")
	}
	if member.MemberType != "user" && member.MemberType != "assistant" {
		return errors.New("conversation membership memberType is invalid")
	}
	if member.Role != "owner" && member.Role != "admin" && member.Role != "member" {
		return errors.New("conversation membership role is invalid")
	}
	if member.MemberType == "assistant" && member.Role != "member" {
		return errors.New("assistant membership role must be member")
	}
	return nil
}

type ListSort string

const (
	ListSortJoinedAsc      ListSort = "joined_asc"
	ListSortDisplayNameAsc ListSort = "display_name_asc"
)

func NormalizeListSort(raw string) ListSort {
	if strings.TrimSpace(raw) == string(ListSortDisplayNameAsc) {
		return ListSortDisplayNameAsc
	}
	return ListSortJoinedAsc
}

type ListQuery struct {
	Limit  int
	Cursor string
	Role   string
	Query  string
	Sort   ListSort
}

func EncodeDisplayNameCursor(displayName, userID string) string {
	payload, _ := json.Marshal(struct {
		DisplayName string `json:"d"`
		UserID      string `json:"u"`
	}{DisplayName: displayName, UserID: userID})
	return base64.RawURLEncoding.EncodeToString(payload)
}

func EncodeJoinedCursor(joinedAt time.Time, id string) string {
	payload, _ := json.Marshal(struct {
		JoinedAtUnixNanos int64  `json:"t"`
		ID                string `json:"i"`
	}{JoinedAtUnixNanos: joinedAt.UTC().UnixNano(), ID: id})
	return base64.RawURLEncoding.EncodeToString(payload)
}
