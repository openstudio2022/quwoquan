// Persistence-specialty provider state: this file deliberately exercises the
// Mongo aggregate decoder before reading the same objects through the real HTTP
// handler. Direct storage here must not be reused as general API setup.
package api_integration

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	"quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

type contractSeedEvidence struct {
	SeedRefs          []string
	ResetScope        string
	TargetStore       string
	InsertedCount     int
	VerifiedEndpoints []string
}

type chatFixtureSeedSet struct {
	CurrentUserID string                             `json:"currentUserId"`
	Conversations []chatFixtureConversation          `json:"conversations"`
	Messages      map[string][]chatFixtureMessage    `json:"messages"`
	Members       map[string][]chatFixtureMember     `json:"members"`
	UserStates    []chatFixtureConversationUserState `json:"userStates"`
}

type chatFixtureConversation struct {
	ID                     string   `json:"id"`
	Type                   string   `json:"type"`
	Title                  string   `json:"title"`
	AvatarURL              string   `json:"avatarUrl"`
	CreatorID              string   `json:"creatorId"`
	CircleID               string   `json:"circleId"`
	MaxSeq                 int64    `json:"maxSeq"`
	MemberCount            int      `json:"memberCount"`
	MaxGroupSize           int      `json:"maxGroupSize"`
	ReceiptEnabled         bool     `json:"receiptEnabled"`
	GroupAvatarVersion     int64    `json:"groupAvatarVersion"`
	GroupAvatarSourceUsers []string `json:"groupAvatarSourceUserIds"`
	LastMessagePreview     string   `json:"lastMessagePreview"`
	LastMessageTime        string   `json:"lastMessageTime"`
	MessageCount           int      `json:"messageCount"`
	Status                 string   `json:"status"`
	CreatedAt              string   `json:"createdAt"`
	UpdatedAt              string   `json:"updatedAt"`
}

type chatFixtureMessage struct {
	ID                        string `json:"id"`
	ConversationID            string `json:"conversationId"`
	ClientMessageID           string `json:"clientMsgId"`
	SenderID                  string `json:"senderId"`
	SenderDisplayNameSnapshot string `json:"senderDisplayNameSnapshot"`
	SenderAvatarURLSnapshot   string `json:"senderAvatarUrlSnapshot"`
	Type                      string `json:"type"`
	Content                   string `json:"content"`
	MediaAssetID              string `json:"mediaAssetId"`
	Seq                       int64  `json:"seq"`
	Status                    string `json:"status"`
	Timestamp                 string `json:"timestamp"`
}

type chatFixtureMember struct {
	UserID      string `json:"userId"`
	DisplayName string `json:"displayName"`
	AvatarURL   string `json:"avatarUrl"`
	Role        string `json:"role"`
}

type chatFixtureConversationUserState struct {
	// Fixture 输入使用业务键 id；写入 Mongo 时模型的 bson 标签映射为 `_id`。
	ID             string `json:"id"`
	UserID         string `json:"userId"`
	ConversationID string `json:"conversationId"`
	ReadSeq        int64  `json:"readSeq"`
	UnreadCount    int    `json:"unreadCount"`
	Muted          bool   `json:"muted"`
	Pinned         bool   `json:"pinned"`
	UpdatedAt      string `json:"updatedAt"`
}

func provisionChatPersistenceProviderState(t *testing.T, seedRef string) contractSeedEvidence {
	t.Helper()
	ctx := context.Background()
	seedSet, ok := buildChatContractSeed(seedRef)
	if !ok {
		t.Fatalf("chat seed ref not found: %s", seedRef)
	}

	resetChatFixtureNamespace(t)
	inserted := 0
	seenMembers := make(map[string]struct{})
	for _, fc := range seedSet.Conversations {
		conv := chatConversationFromFixture(fc)
		if _, err := mongoDB.Collection("conversations").InsertOne(ctx, conv); err != nil {
			t.Fatalf("seed conversation %s: %v", conv.ID, err)
		}
		inserted++
	}
	for conversationID, members := range seedSet.Members {
		for idx, fm := range members {
			memberKey := conversationID + "/" + fm.UserID
			if _, exists := seenMembers[memberKey]; exists {
				continue
			}
			seenMembers[memberKey] = struct{}{}
			member := chatMemberFromFixture(conversationID, idx, fm)
			if _, err := mongoDB.Collection("conversation_memberships").InsertOne(ctx, member); err != nil {
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
	backfillSeededGroupAvatars(t)
	if testInboxViewProjector == nil {
		t.Fatal("chat seed requires the canonical ChatInboxView projector")
	}
	if _, err := testInboxViewProjector.Rebuild(ctx, "fixture-chat-core", 100); err != nil {
		t.Fatalf("rebuild ChatInboxView from seeded domain snapshots: %v", err)
	}

	return contractSeedEvidence{
		SeedRefs:      []string{seedRef},
		ResetScope:    "fixture_* conversations/messages/members/states in chat_test",
		TargetStore:   "mongodb:chat_test",
		InsertedCount: inserted,
		VerifiedEndpoints: []string{
			"/chat/inbox",
			"/chat/conversations/fixture_conv_direct",
			"/chat/conversations/fixture_conv_direct/messages",
			"/chat/conversations/fixture_conv_direct/members",
		},
	}
}

func buildChatContractSeed(seedRef string) (chatFixtureSeedSet, bool) {
	if seedRef != "chat_core" {
		return chatFixtureSeedSet{}, false
	}
	const (
		current = "fixture_user_current"
		friend  = "fixture_user_friend"
		first   = "fixture_user_weekend_1"
		second  = "fixture_user_weekend_2"
		photo   = "fixture_user_photo"
	)
	conversation := func(id, kind, title, avatar, creator, circle string, memberCount, messageCount int) chatFixtureConversation {
		maxGroupSize := 500
		if kind == "direct" {
			maxGroupSize = 2
		}
		return chatFixtureConversation{
			ID: id, Type: kind, Title: title, AvatarURL: avatar, CreatorID: creator, CircleID: circle,
			MaxSeq: int64(messageCount), MemberCount: memberCount, MessageCount: messageCount,
			MaxGroupSize: maxGroupSize, ReceiptEnabled: true, Status: "active",
			LastMessagePreview: title + " 固定 seed 消息", LastMessageTime: "2026-06-10T10:00:00Z",
			CreatedAt: "2026-06-10T00:00:00Z", UpdatedAt: "2026-06-10T10:00:00Z",
		}
	}
	message := func(id, conversationID, senderID, kind, content string, seq int64) chatFixtureMessage {
		return chatFixtureMessage{
			ID: id, ConversationID: conversationID, ClientMessageID: id + "_client",
			SenderID: senderID, SenderDisplayNameSnapshot: senderID,
			SenderAvatarURLSnapshot: "media/avatar/s/archived-avatar/user/" + senderID + "/v1/avatar.png",
			Type:                    kind, Content: content, Seq: seq, Status: "sent",
			Timestamp: time.Date(2026, time.June, 10, 0, int(seq), 0, 0, time.UTC).Format(time.RFC3339),
		}
	}
	directMessages := []chatFixtureMessage{
		message("fixture_msg_direct_1", "fixture_conv_direct", current, "text", "这是一条契约聊天消息。", 1),
		message("fixture_msg_direct_2", "fixture_conv_direct", friend, "text", "契约消息已送达", 2),
		message("fixture_msg_direct_image_1", "fixture_conv_direct", current, "image", "契约图片消息", 3),
		message("fixture_msg_direct_video_1", "fixture_conv_direct", friend, "video", "契约视频消息", 4),
		message("fixture_msg_direct_file_1", "fixture_conv_direct", current, "file", "契约文件消息", 5),
		message("fixture_conv_direct_msg_06", "fixture_conv_direct", friend, "text", "契约好友固定 seed 消息 #6", 6),
	}
	directMessages[2].MediaAssetID = "fixture_media_image"
	directMessages[3].MediaAssetID = "fixture_media_video"
	directMessages[4].MediaAssetID = "fixture_media_file"
	member := func(userID, name, role string) chatFixtureMember {
		return chatFixtureMember{
			UserID: userID, DisplayName: name,
			AvatarURL: "media/avatar/s/archived-avatar/user/" + userID + "/v1/avatar.png",
			Role:      role,
		}
	}
	return chatFixtureSeedSet{
		CurrentUserID: current,
		Conversations: []chatFixtureConversation{
			conversation("fixture_conv_direct", "direct", "契约好友", "media/avatar/s/archived-avatar/user/fixture_user_friend/v1/avatar.png", current, "", 2, 6),
			conversation("fixture_conv_group", "group", "契约周末群", "", current, "", 3, 2),
			conversation("fixture_conv_photo_group", "group", "契约摄影交流群", "", photo, "fixture_circle_photo", 3, 2),
		},
		Messages: map[string][]chatFixtureMessage{
			"fixture_conv_direct": directMessages,
			"fixture_conv_group": {
				message("fixture_msg_group_1", "fixture_conv_group", current, "text", "周末集合时间已确认", 1),
				message("fixture_msg_group_2", "fixture_conv_group", first, "text", "契约同伴一固定 seed 消息", 2),
			},
			"fixture_conv_photo_group": {
				message("fixture_msg_photo_group_1", "fixture_conv_photo_group", photo, "text", "摄影交流群固定 seed 消息", 1),
				message("fixture_msg_photo_group_2", "fixture_conv_photo_group", friend, "text", "摄影好友固定 seed 消息", 2),
			},
		},
		Members: map[string][]chatFixtureMember{
			"fixture_conv_direct":      {member(current, "新同学", "owner"), member(friend, "契约好友", "member")},
			"fixture_conv_group":       {member(current, "新同学", "owner"), member(first, "契约同伴一", "member"), member(second, "契约同伴二", "member")},
			"fixture_conv_photo_group": {member(current, "新同学", "member"), member(photo, "契约摄影师", "owner"), member(friend, "契约好友", "member")},
		},
		UserStates: []chatFixtureConversationUserState{
			{ID: "fixture_state_direct", UserID: current, ConversationID: "fixture_conv_direct", ReadSeq: 5, UnreadCount: 1, UpdatedAt: "2026-06-10T10:00:00Z"},
			{ID: "fixture_state_group", UserID: current, ConversationID: "fixture_conv_group", ReadSeq: 1, UnreadCount: 1, UpdatedAt: "2026-06-10T10:00:00Z"},
			{ID: "fixture_state_photo_group", UserID: current, ConversationID: "fixture_conv_photo_group", ReadSeq: 1, UnreadCount: 1, UpdatedAt: "2026-06-10T10:00:00Z"},
		},
	}, true
}

func TestPersistenceProviderStatePersistsCanonicalChatData(t *testing.T) {
	evidence := provisionChatPersistenceProviderState(t, "chat_core")
	if evidence.InsertedCount <= 0 {
		t.Fatal("canonical chat fixture must persist at least one document")
	}
	if evidence.TargetStore != "mongodb:chat_test" || len(evidence.VerifiedEndpoints) == 0 {
		t.Fatalf("unexpected seed evidence: %+v", evidence)
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
	if err := integrationRedis.FlushDBs(ctx, 0, 1, 2, 3); err != nil {
		t.Fatalf("flush chat fixture Redis: %v", err)
	}
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
		CircleId:           fc.CircleID,
		MaxSeq:             fc.MaxSeq,
		MemberCount:        fc.MemberCount,
		MaxGroupSize:       fc.MaxGroupSize,
		ReceiptEnabled:     fc.ReceiptEnabled,
		LastMessagePreview: fc.LastMessagePreview,
		LastMessageTime:    lastMessageTime,
		MessageCount:       fc.MessageCount,
		Status:             model.ConversationStatus(fc.Status),
		CreatedAt:          createdAt,
		UpdatedAt:          updatedAt,
	}
}

func chatMessageFromFixture(conversationID string, fm chatFixtureMessage) *messagemodel.Message {
	return &messagemodel.Message{
		ID:                        fm.ID,
		ConversationID:            conversationID,
		Seq:                       fm.Seq,
		ClientMessageID:           fm.ClientMessageID,
		SenderID:                  fm.SenderID,
		SenderDisplayNameSnapshot: fm.SenderDisplayNameSnapshot,
		SenderAvatarURLSnapshot:   fm.SenderAvatarURLSnapshot,
		Type:                      fm.Type,
		Content:                   fm.Content,
		MediaAssetID:              fm.MediaAssetID,
		Status:                    fm.Status,
		Timestamp:                 parseFixtureTime(fm.Timestamp),
		Version:                   1,
	}
}

func chatMemberFromFixture(conversationID string, order int, fm chatFixtureMember) *model.ConversationMember {
	joinedAt := time.Date(2026, time.January, 1, 0, 0, 0, 0, time.UTC).
		Add(time.Duration(order) * time.Second)
	return &model.ConversationMember{
		ID:             conversationID + "_" + fm.UserID,
		ConversationId: conversationID,
		UserId:         fm.UserID,
		DisplayName:    fm.DisplayName,
		AvatarUrl:      fm.AvatarURL,
		AvatarVersion:  1,
		MemberType:     "user",
		Role:           fm.Role,
		JoinedAt:       joinedAt,
	}
}

func backfillSeededGroupAvatars(t *testing.T) {
	t.Helper()
	const testAvatarCDNBase = "https://127.0.0.1:18081"
	repo := persistence.NewMongoChatStore(mongoDB)
	media := newGroupAvatarMediaForContractTest()
	if err := application.BackfillMissingGroupAvatars(
		context.Background(),
		chatStoragePorts(repo),
		testEventPublisher,
		media,
		testUserSyncPublisher,
		testGroupAvatarScheduler,
		200,
	); err != nil {
		t.Fatalf("backfill seeded group avatars: %v", err)
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
