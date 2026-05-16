package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/contractfixture"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

const chatScenarioFixturePath = "messages/chat/test_fixtures/scenarios/chat_scenarios.json"

type multiFlag []string

func (m *multiFlag) String() string {
	return strings.Join(*m, ",")
}

func (m *multiFlag) Set(value string) error {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil
	}
	*m = append(*m, trimmed)
	return nil
}

type chatFixturePack struct {
	SeedSets map[string]chatFixtureSeedSet `json:"seedSets"`
}

type chatFixtureSeedSet struct {
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
	CircleID           string `json:"circleId"`
	MaxSeq             int64  `json:"maxSeq"`
	MemberCount        int    `json:"memberCount"`
	MaxGroupSize       int    `json:"maxGroupSize"`
	ReceiptEnabled     bool   `json:"receiptEnabled"`
	GroupAvatarVersion int64  `json:"groupAvatarVersion"`
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

type seedCounts struct {
	conversations int
	members       int
	messages      int
	userStates    int
}

func main() {
	var seedRefs multiFlag
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "MongoDB connection URI")
	database := flag.String("database", "quwoquan_chat_local", "MongoDB database name")
	flag.Var(&seedRefs, "seed-ref", "chat seed ref to load (repeatable)")
	flag.Parse()

	if len(seedRefs) == 0 {
		seedRefs = append(seedRefs, "chat_core")
	}

	pack, err := contractfixture.LoadMetadataJSON[chatFixturePack](chatScenarioFixturePath)
	if err != nil {
		log.Fatalf("load chat fixture pack: %v", err)
	}

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(strings.TrimSpace(*mongoURI)))
	if err != nil {
		log.Fatalf("connect mongo: %v", err)
	}
	defer func() { _ = client.Disconnect(ctx) }()

	db := client.Database(strings.TrimSpace(*database))
	if err := resetChatFixtureNamespace(ctx, db); err != nil {
		log.Fatalf("reset chat fixture namespace: %v", err)
	}

	counts, err := seedChatFixtureRefs(ctx, db, pack, seedRefs)
	if err != nil {
		log.Fatalf("seed chat fixture refs: %v", err)
	}
	log.Printf(
		"seeded chat fixture refs=%s db=%s conversations=%d members=%d messages=%d states=%d",
		strings.Join(seedRefs, ","),
		db.Name(),
		counts.conversations,
		counts.members,
		counts.messages,
		counts.userStates,
	)
}

func seedChatFixtureRefs(
	ctx context.Context,
	db *mongo.Database,
	pack chatFixturePack,
	seedRefs []string,
) (seedCounts, error) {
	counts := seedCounts{}
	seenConversations := map[string]struct{}{}
	seenMembers := map[string]struct{}{}
	seenMessages := map[string]struct{}{}
	seenStates := map[string]struct{}{}

	for _, ref := range seedRefs {
		seedSet, ok := pack.SeedSets[ref]
		if !ok {
			return counts, fmt.Errorf("chat seed ref not found: %s", ref)
		}

		for _, fixtureConversation := range seedSet.Conversations {
			conv := chatConversationFromFixture(fixtureConversation)
			if _, exists := seenConversations[conv.ID]; exists {
				continue
			}
			if _, err := db.Collection("conversations").InsertOne(ctx, conv); err != nil {
				return counts, fmt.Errorf("insert conversation %s: %w", conv.ID, err)
			}
			seenConversations[conv.ID] = struct{}{}
			counts.conversations++
		}

		for conversationID, fixtureMembers := range seedSet.Members {
			for index, fixtureMember := range fixtureMembers {
				member := chatMemberFromFixture(conversationID, index, fixtureMember)
				if _, exists := seenMembers[member.ID]; exists {
					continue
				}
				if _, err := db.Collection("conversation_members").InsertOne(ctx, member); err != nil {
					return counts, fmt.Errorf("insert member %s: %w", member.ID, err)
				}
				seenMembers[member.ID] = struct{}{}
				counts.members++
			}
		}

		for conversationID, fixtureMessages := range seedSet.Messages {
			for _, fixtureMessage := range fixtureMessages {
				msg := chatMessageFromFixture(conversationID, fixtureMessage)
				if _, exists := seenMessages[msg.ID]; exists {
					continue
				}
				if _, err := db.Collection("messages").InsertOne(ctx, msg); err != nil {
					return counts, fmt.Errorf("insert message %s: %w", msg.ID, err)
				}
				seenMessages[msg.ID] = struct{}{}
				counts.messages++
			}
		}

		for _, fixtureState := range seedSet.UserStates {
			state := chatUserStateFromFixture(fixtureState)
			if _, exists := seenStates[state.ID]; exists {
				continue
			}
			if _, err := db.Collection("conversation_user_states").InsertOne(ctx, state); err != nil {
				return counts, fmt.Errorf("insert user state %s: %w", state.ID, err)
			}
			seenStates[state.ID] = struct{}{}
			counts.userStates++
		}
	}

	return counts, nil
}

func resetChatFixtureNamespace(ctx context.Context, db *mongo.Database) error {
	for _, name := range []string{
		"conversations",
		"messages",
		"conversation_members",
		"conversation_user_states",
		"message_receipts",
	} {
		if _, err := db.Collection(name).DeleteMany(ctx, bson.M{
			"$or": []bson.M{
				{"_id": bson.M{"$regex": "^fixture_"}},
				{"conversationId": bson.M{"$regex": "^fixture_"}},
				{"userId": bson.M{"$regex": "^fixture_"}},
				{"messageId": bson.M{"$regex": "^fixture_"}},
			},
		}); err != nil {
			return fmt.Errorf("reset collection %s: %w", name, err)
		}
	}
	return nil
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
		GroupAvatarVersion: fc.GroupAvatarVersion,
		CreatorId:          fc.CreatorID,
		CircleId:           fc.CircleID,
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
	id := strings.TrimSpace(fm.ID)
	if id == "" {
		id = strings.TrimSpace(fm.MessageID)
	}
	msgType := strings.TrimSpace(fm.Type)
	if msgType == "" {
		msgType = strings.TrimSpace(fm.MessageType)
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

func chatUserStateFromFixture(fs chatFixtureConversationUserState) *model.ConversationUserState {
	updatedAt := parseFixtureTime(fs.UpdatedAt)
	return &model.ConversationUserState{
		ID:             fs.ID,
		UserId:         fs.UserID,
		ConversationId: fs.ConversationID,
		ReadSeq:        fs.ReadSeq,
		UnreadCount:    fs.UnreadCount,
		Muted:          fs.Muted,
		Pinned:         fs.Pinned,
		LastReadAt:     updatedAt,
		UpdatedAt:      updatedAt,
	}
}

func parseFixtureTime(value string) time.Time {
	if parsed, err := time.Parse(time.RFC3339, strings.TrimSpace(value)); err == nil {
		return parsed
	}
	return time.Now().UTC()
}
