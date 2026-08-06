// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
// readiness_case: project-gathering-conversation-local
// readiness_case: get-gathering-chat-board-local
package local_contract

import (
	"context"
	"strings"
	"testing"
	"time"

	chatapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

func TestGatheringConversationProjectionKeepsSoleGroupAndMonotonicPolicy(t *testing.T) {
	store := newCircleGroupChatSyncMemoryStore()
	commands := newMemoryAggregateCommandStore()
	messages := &gatheringBoardMessageStore{}
	service := chatapp.NewConversationService(
		chatapp.ChatStoragePorts{
			Transactions: passthroughTransactionRunner{}, Conversations: store,
			GatheringConversations: store, Messages: messages, Members: store, UserStates: store,
			ConversationCommands: commands,
		},
		noopCache{}, syncNoopEventPublisher{}, nil, nil, nil, nil, syncNoopGroupAvatarScheduler{},
	)
	request := chatapp.GatheringConversationProvisioningRequest{
		SourceEventID: "gathering-2:create:1", SourceVersion: 1,
		GatheringID: "gathering-2", OwnerPersonaID: "owner-2", Title: "双人同行",
		AccessMode:    chatapp.ConversationAccessModeActive,
		PostingPolicy: chatapp.ConversationPostingPolicyMemberChat,
	}
	conversation, err := service.ProvisionGatheringConversation(context.Background(), request)
	if err != nil {
		t.Fatalf("ProvisionGatheringConversation: %v", err)
	}
	if conversation.Type != "group" || conversation.OriginType != "gathering" ||
		conversation.GatheringId != request.GatheringID || conversation.MaxGroupSize != 1000 {
		t.Fatalf("Gathering room must stay a Chat group independent of Circle capacity=2: %+v", conversation)
	}
	replayed, err := service.ProvisionGatheringConversation(context.Background(), request)
	if err != nil || replayed.ID != conversation.ID || len(store.conversations) != 1 {
		t.Fatalf("exact room replay must return sole binding: replay=%+v err=%v count=%d", replayed, err, len(store.conversations))
	}

	announcementOnly := request
	announcementOnly.SourceEventID = "gathering-2:announcement-policy:2"
	announcementOnly.SourceVersion = 2
	announcementOnly.PostingPolicy = chatapp.ConversationPostingPolicyAnnouncementsOnly
	projected, err := service.ProvisionGatheringConversation(context.Background(), announcementOnly)
	if err != nil {
		t.Fatalf("project announcements_only: %v", err)
	}
	if projected.AccessMode != chatapp.ConversationAccessModeActive ||
		projected.PostingPolicy != chatapp.ConversationPostingPolicyAnnouncementsOnly {
		t.Fatalf("Gathering posting policy did not converge: %+v", projected)
	}

	readOnly := announcementOnly
	readOnly.SourceEventID = "gathering-2:cancelled:3"
	readOnly.SourceVersion = 3
	readOnly.AccessMode = chatapp.ConversationAccessModeReadOnly
	projected, err = service.ProvisionGatheringConversation(context.Background(), readOnly)
	if err != nil {
		t.Fatalf("project read_only: %v", err)
	}
	if projected.AccessMode != chatapp.ConversationAccessModeReadOnly || projected.ID != conversation.ID {
		t.Fatalf("cancelled Gathering must retain room and become read_only: %+v", projected)
	}
	stale, err := service.ProvisionGatheringConversation(context.Background(), request)
	if err != nil || stale.AccessMode != chatapp.ConversationAccessModeReadOnly ||
		stale.PostingPolicy != chatapp.ConversationPostingPolicyAnnouncementsOnly ||
		stale.GatheringSourceVersion != 3 {
		t.Fatalf("old source version regressed policy: value=%+v err=%v", stale, err)
	}
	conflict := readOnly
	conflict.PostingPolicy = chatapp.ConversationPostingPolicyMemberChat
	if _, err := service.ProvisionGatheringConversation(context.Background(), conflict); err == nil {
		t.Fatal("same sourceVersion with different policy must fail closed")
	}

	now := time.Now().UTC()
	stored := store.conversations[conversation.ID]
	stored.Announcement = "集合点调整"
	stored.AnnouncementUpdatedBy = "owner-2"
	stored.AnnouncementUpdatedAt = &now
	messages.messages = []messagemodel.Message{{
		ID: "message-asset-1", ConversationID: conversation.ID, Seq: 7,
		Type: "image", MediaAssetID: "asset-1", Status: "sent", Timestamp: now,
	}}
	board, err := service.GetGatheringChatBoard(context.Background(), conversation.ID, "owner-2")
	if err != nil {
		t.Fatalf("GetGatheringChatBoard: %v", err)
	}
	if board.Access.CanPost || board.Access.AccessMode != chatapp.ConversationAccessModeReadOnly ||
		board.PinnedAnnouncement == nil || board.PinnedAnnouncement.Content != "集合点调整" ||
		len(board.Assets) != 1 || board.Assets[0].MediaAssetID != "asset-1" {
		t.Fatalf("Board Chat slice did not reuse access/announcement/message asset owners: %+v", board)
	}
	for _, event := range commands.events {
		if strings.Contains(event.EventType, "Board") ||
			strings.Contains(event.EventType, "GatheringMessage") ||
			strings.Contains(event.EventType, "Workspace") {
			t.Fatalf("Board query introduced a forbidden aggregate/event: %+v", event)
		}
	}
}

type gatheringBoardMessageStore struct {
	chatapp.MessageStore
	messages []messagemodel.Message
}

func (store *gatheringBoardMessageStore) ListMessages(
	context.Context,
	string,
	int,
	int64,
	int64,
) ([]messagemodel.Message, error) {
	return append([]messagemodel.Message(nil), store.messages...), nil
}
