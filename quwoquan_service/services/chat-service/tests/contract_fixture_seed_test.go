package tests

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/runtime/contractfixture"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type chatFixturePack struct {
	SeedSets map[string]chatFixtureSeedSet `json:"seedSets"`
}

type chatFixtureSeedSet struct {
	CurrentUserID string                             `json:"currentUserId"`
	Conversations []chatFixtureConversation          `json:"conversations"`
	Messages      map[string][]chatFixtureMessage    `json:"messages"`
	Members       map[string][]chatFixtureMember     `json:"members"`
	UserStates    []chatFixtureConversationUserState `json:"userStates"`
}

type chatFixtureConversation struct {
	ID                 string `json:"_id"`
	Type               string `json:"type"`
	Title              string `json:"title"`
	AvatarURL          string `json:"avatarUrl"`
	CreatorID          string `json:"creatorId"`
	MaxSeq             int64  `json:"maxSeq"`
	MemberCount        int    `json:"memberCount"`
	MaxGroupSize       int    `json:"maxGroupSize"`
	ReceiptEnabled     bool   `json:"receiptEnabled"`
	LastMessagePreview string `json:"lastMessagePreview"`
	LastMessageTime    string `json:"lastMessageTime"`
	MessageCount       int    `json:"messageCount"`
	Status             string `json:"status"`
	CreatedAt          string `json:"createdAt"`
	UpdatedAt          string `json:"updatedAt"`
}

type chatFixtureMessage struct {
	ID             string `json:"_id"`
	MessageID      string `json:"messageId"`
	ConversationID string `json:"conversationId"`
	SenderID       string `json:"senderId"`
	Type           string `json:"type"`
	MessageType    string `json:"messageType"`
	Content        string `json:"content"`
	Seq            int64  `json:"seq"`
	CreatedAt      string `json:"createdAt"`
}

type chatFixtureMember struct {
	UserID      string `json:"userId"`
	DisplayName string `json:"displayName"`
	AvatarURL   string `json:"avatarUrl"`
	Role        string `json:"role"`
}

type chatFixtureConversationUserState struct {
	ID             string `json:"_id"`
	UserID         string `json:"userId"`
	ConversationID string `json:"conversationId"`
	ReadSeq        int64  `json:"readSeq"`
	UnreadCount    int    `json:"unreadCount"`
	Muted          bool   `json:"muted"`
	Pinned         bool   `json:"pinned"`
	UpdatedAt      string `json:"updatedAt"`
}

func seedChatContractFixture(t *testing.T, seedRef string) contractSeedEvidence {
	t.Helper()
	ctx := context.Background()
	pack, err := contractfixture.LoadMetadataJSON[chatFixturePack](
		"messages/chat/test_fixtures/scenarios/chat_scenarios.json",
	)
	if err != nil {
		t.Fatalf("load chat fixture: %v", err)
	}
	seedSet, ok := pack.SeedSets[seedRef]
	if !ok {
		t.Fatalf("chat seed ref not found: %s", seedRef)
	}

	resetChatFixtureNamespace(t)
	inserted := 0
	for _, fc := range seedSet.Conversations {
		conv := chatConversationFromFixture(fc)
		if _, err := mongoDB.Collection("conversations").InsertOne(ctx, conv); err != nil {
			t.Fatalf("seed conversation %s: %v", conv.ID, err)
		}
		inserted++
	}
	for conversationID, members := range seedSet.Members {
		for _, fm := range members {
			member := chatMemberFromFixture(conversationID, fm)
			if _, err := mongoDB.Collection("conversation_members").InsertOne(ctx, member); err != nil {
				t.Fatalf("seed member %s/%s: %v", conversationID, fm.UserID, err)
			}
			inserted++
		}
	}
	for conversationID, messages := range seedSet.Messages {
		for _, fm := range messages {
			msg := chatMessageFromFixture(conversationID, fm)
			if _, err := mongoDB.Collection("messages").InsertOne(ctx, msg); err != nil {
				t.Fatalf("seed message %s: %v", msg.ID, err)
			}
			inserted++
		}
	}
	for _, fs := range seedSet.UserStates {
		state := chatUserStateFromFixture(fs)
		if _, err := mongoDB.Collection("conversation_user_states").InsertOne(ctx, state); err != nil {
			t.Fatalf("seed user state %s: %v", state.ID, err)
		}
		inserted++
	}

	return contractSeedEvidence{
		SeedRefs:      []string{seedRef},
		ResetScope:    "fixture_* conversations/messages/members/states in chat_test",
		TargetStore:   "mongodb:chat_test",
		InsertedCount: inserted,
		VerifiedEndpoints: []string{
			"/v1/chat/inbox",
			"/v1/chat/conversations/fixture_conv_direct",
			"/v1/chat/conversations/fixture_conv_direct/messages",
			"/v1/chat/conversations/fixture_conv_direct/members",
		},
	}
}

func resetChatFixtureNamespace(t *testing.T) {
	t.Helper()
	ctx := context.Background()
	for _, name := range collections {
		_, err := mongoDB.Collection(name).DeleteMany(ctx, bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"conversationId": bson.M{"$regex": "^fixture_"}},
				{"userId": bson.M{"$regex": "^fixture_"}},
				{"messageId": bson.M{"$regex": "^fixture_"}},
			},
		})
		if err != nil {
			t.Fatalf("reset chat fixture namespace %s: %v", name, err)
		}
	}
	mr.FlushAll()
}

func chatConversationFromFixture(fc chatFixtureConversation) *model.Conversation {
	createdAt := parseFixtureTime(fc.CreatedAt)
	updatedAt := parseFixtureTime(fc.UpdatedAt)
	lastMessageTime := parseFixtureTime(fc.LastMessageTime)
	return &model.Conversation{
		ID:                 fc.ID,
		Type:               fc.Type,
		Title:              fc.Title,
		AvatarUrl:          fc.AvatarURL,
		CreatorId:          fc.CreatorID,
		MaxSeq:             fc.MaxSeq,
		MemberCount:        fc.MemberCount,
		MaxGroupSize:       fc.MaxGroupSize,
		ReceiptEnabled:     fc.ReceiptEnabled,
		LastMessagePreview: fc.LastMessagePreview,
		LastMessageTime:    lastMessageTime,
		MessageCount:       fc.MessageCount,
		Status:             fc.Status,
		CreatedAt:          createdAt,
		UpdatedAt:          updatedAt,
	}
}

func chatMessageFromFixture(conversationID string, fm chatFixtureMessage) *model.Message {
	id := fm.ID
	if id == "" {
		id = fm.MessageID
	}
	msgType := fm.Type
	if msgType == "" {
		msgType = fm.MessageType
	}
	return &model.Message{
		ID:             id,
		ConversationId: conversationID,
		Seq:            fm.Seq,
		ClientMsgId:    id + "_client",
		SenderId:       fm.SenderID,
		Type:           msgType,
		Content:        fm.Content,
		Status:         "sent",
		Timestamp:      parseFixtureTime(fm.CreatedAt),
	}
}

func chatMemberFromFixture(conversationID string, fm chatFixtureMember) *model.ConversationMember {
	return &model.ConversationMember{
		ID:             conversationID + "_" + fm.UserID,
		ConversationId: conversationID,
		UserId:         fm.UserID,
		DisplayName:    fm.DisplayName,
		AvatarUrl:      fm.AvatarURL,
		AvatarVersion:  1,
		MemberType:     "user",
		Role:           fm.Role,
		JoinedAt:       time.Now().UTC(),
	}
}

func chatUserStateFromFixture(fs chatFixtureConversationUserState) *model.ConversationUserState {
	return &model.ConversationUserState{
		ID:             fs.ID,
		UserId:         fs.UserID,
		ConversationId: fs.ConversationID,
		ReadSeq:        fs.ReadSeq,
		UnreadCount:    fs.UnreadCount,
		Muted:          fs.Muted,
		Pinned:         fs.Pinned,
		LastReadAt:     parseFixtureTime(fs.UpdatedAt),
		UpdatedAt:      parseFixtureTime(fs.UpdatedAt),
	}
}

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, value); err == nil {
		return parsed
	}
	return time.Now().UTC()
}
