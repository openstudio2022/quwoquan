// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
// readiness_case: project-gathering-conversation-membership-api
package api_integration

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	conversationpersistence "quwoquan_service/services/chat-service/internal/chat/conversation/infrastructure/persistence"
	membershiphttp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/adapters/inbound/http"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
	userstatepersistence "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/infrastructure/persistence"
)

type realGatheringBindingReader struct {
	store *conversationpersistence.MongoChatStore
}

func (reader realGatheringBindingReader) ReadGatheringConversation(
	ctx context.Context,
	gatheringID string,
) (membershipapp.GatheringBinding, bool, error) {
	conversation, err := reader.store.FindConversationByGatheringID(ctx, gatheringID)
	if errors.Is(err, conversationmodel.ErrConversationNotFound) {
		return membershipapp.GatheringBinding{}, false, nil
	}
	if err != nil {
		return membershipapp.GatheringBinding{}, false, err
	}
	return membershipapp.GatheringBinding{
		GatheringID: conversation.GatheringId, ConversationID: conversation.ID,
		Active: conversation.Status == conversationmodel.ConversationStatusActive,
	}, true, nil
}

type realGatheringUserStateWriter struct {
	store *userstatepersistence.MongoStore
}

func (writer realGatheringUserStateWriter) EnsureGatheringUserState(
	ctx context.Context,
	personaID string,
	conversationID string,
	occurredAt time.Time,
) error {
	return writer.store.UpsertUserState(ctx, &userstatemodel.State{
		ID:     "gathering:" + conversationID + ":" + personaID,
		UserId: personaID, ConversationId: conversationID, UpdatedAt: occurredAt.UTC(),
	})
}

func (writer realGatheringUserStateWriter) DeleteGatheringUserState(
	ctx context.Context,
	personaID string,
	conversationID string,
) error {
	return writer.store.DeleteUserState(ctx, personaID, conversationID)
}

type realGatheringRosterWriter struct {
	store *conversationpersistence.MongoChatStore
}

func (writer realGatheringRosterWriter) BumpGatheringRoster(
	ctx context.Context,
	conversationID string,
	memberCount int,
) error {
	return writer.store.BumpMembersRosterRevision(ctx, conversationID, &memberCount)
}

type realGatheringProfileReader struct{}

func (realGatheringProfileReader) ReadGatheringMemberProfile(
	_ context.Context,
	personaID string,
) (membershipapp.GatheringMemberProfile, error) {
	return membershipapp.GatheringMemberProfile{
		UserHandle: "@" + personaID, DisplayName: personaID,
	}, nil
}

type realGatheringOutbox struct {
	membership   *conversationpersistence.MongoAggregateCommandStore
	conversation *conversationpersistence.MongoAggregateCommandStore
}

func (outbox realGatheringOutbox) AppendGatheringProjectionEvents(
	ctx context.Context,
	membershipEvents []membershipapp.GatheringOutboxEvent,
	conversationEvents []membershipapp.GatheringOutboxEvent,
) error {
	if err := outbox.membership.AppendAggregateOutboxEvents(ctx, convertGatheringEvents(membershipEvents)); err != nil {
		return err
	}
	return outbox.conversation.AppendAggregateOutboxEvents(ctx, convertGatheringEvents(conversationEvents))
}

func convertGatheringEvents(events []membershipapp.GatheringOutboxEvent) []conversationapp.AggregateOutboxEvent {
	converted := make([]conversationapp.AggregateOutboxEvent, 0, len(events))
	for _, event := range events {
		converted = append(converted, conversationapp.AggregateOutboxEvent{
			EventID: event.EventID, EventType: event.EventType, AggregateID: event.AggregateID,
			ConversationID: event.ConversationID, ActorID: event.ActorID, Payload: event.Payload,
		})
	}
	return converted
}

type failingGatheringOutbox struct{}

func (failingGatheringOutbox) AppendGatheringProjectionEvents(
	context.Context,
	[]membershipapp.GatheringOutboxEvent,
	[]membershipapp.GatheringOutboxEvent,
) error {
	return errors.New("injected outbox failure")
}

func TestGatheringProjectionCommitsMemberUserStateRosterWatermarkAndOutboxAtomically(t *testing.T) {
	ctx := context.Background()
	for _, collection := range []string{
		"conversations", "conversation_memberships", "conversation_user_states",
		"gathering_membership_projection_states", "conversation_memberships_outbox",
		"conversations_outbox", "chat_aggregate_outbox_sequences",
	} {
		if _, err := membershipMongoDatabase.Collection(collection).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatal(err)
		}
	}

	chatStore := conversationpersistence.NewMongoChatStore(membershipMongoDatabase)
	if err := chatStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	userStateStore := userstatepersistence.NewMongoStore(membershipMongoDatabase)
	if err := userStateStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	membershipOutbox := conversationpersistence.NewMongoAggregateCommandStore(
		membershipMongoDatabase, "conversation_memberships_command_receipts", "conversation_memberships_outbox",
	)
	conversationOutbox := conversationpersistence.NewMongoAggregateCommandStore(
		membershipMongoDatabase, "conversations_command_receipts", "conversations_outbox",
	)
	for _, store := range []*conversationpersistence.MongoAggregateCommandStore{membershipOutbox, conversationOutbox} {
		if err := store.EnsureIndexes(ctx); err != nil {
			t.Fatal(err)
		}
	}
	now := time.Now().UTC()
	conversation := &conversationmodel.Conversation{
		ID: "conversation-gathering-api", Type: "group", Title: "贡嘎同行",
		CreatorId: "persona-owner", GatheringId: "gathering-api", OriginType: "gathering",
		MaxGroupSize: 8, MemberCount: 1, MembersRosterRevision: 1,
		Status: conversationmodel.ConversationStatusActive, CreatedAt: now, UpdatedAt: now,
	}
	if err := chatStore.CreateConversation(ctx, conversation); err != nil {
		t.Fatal(err)
	}
	owner := &membershipmodel.Member{
		ID: "membership-owner", ConversationId: conversation.ID, UserId: "persona-owner",
		MemberType: "user", Role: "owner", JoinedAt: now,
	}
	if err := membershipStore.CreateMember(ctx, owner); err != nil {
		t.Fatal(err)
	}

	command := membershipapp.GatheringProjectionCommand{
		SourceEventID: "gathering-api:participation:persona-2:20", SourceVersion: 20,
		GatheringID: "gathering-api", PersonaID: "persona-2",
		SourceType: membershipapp.GatheringProjectionSourceParticipation,
		State:      membershipapp.GatheringProjectionStateActive,
	}
	failedFacade := membershipapp.NewGatheringProjectionFacade(
		chatStore, realGatheringBindingReader{chatStore}, membershipStore,
		realGatheringUserStateWriter{userStateStore}, realGatheringRosterWriter{chatStore},
		realGatheringProfileReader{}, membershipStore, failingGatheringOutbox{},
	)
	if _, err := failedFacade.Project(ctx, command); err == nil {
		t.Fatal("injected outbox failure must abort the transaction")
	}
	assertMongoCount(t, "conversation_memberships", bson.M{"userId": "persona-2"}, 0)
	assertMongoCount(t, "conversation_user_states", bson.M{"userId": "persona-2"}, 0)
	assertMongoCount(t, "gathering_membership_projection_states", bson.M{"userId": "persona-2"}, 0)
	stored, err := chatStore.FindConversationByID(ctx, conversation.ID)
	if err != nil || stored.MemberCount != 1 || stored.MembersRosterRevision != 1 {
		t.Fatalf("failed transaction changed roster: value=%+v err=%v", stored, err)
	}

	facade := membershipapp.NewGatheringProjectionFacade(
		chatStore, realGatheringBindingReader{chatStore}, membershipStore,
		realGatheringUserStateWriter{userStateStore}, realGatheringRosterWriter{chatStore},
		realGatheringProfileReader{}, membershipStore,
		realGatheringOutbox{membership: membershipOutbox, conversation: conversationOutbox},
	)
	routes := http.NewServeMux()
	membershiphttp.NewGatheringProjectionHandler(facade).Register(routes)
	request := httptest.NewRequest(
		http.MethodPut,
		"/internal/chat/gathering-conversations/gathering-api/members/persona-2",
		strings.NewReader(`{"sourceEventId":"gathering-api:participation:persona-2:20","sourceVersion":20,"sourceType":"participation","state":"active"}`),
	)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Claims: rtauth.Claims{
			Subject: "service:circle-service", Scope: "chat.gathering.write", Roles: []string{"service"},
		},
		Actor: operation.ActorContext{AccountID: "service:circle-service"},
	}))
	response := httptest.NewRecorder()
	routes.ServeHTTP(response, request)
	if response.Code != http.StatusOK {
		t.Fatalf("project joined status=%d body=%s", response.Code, response.Body.String())
	}
	assertMongoCount(t, "conversation_memberships", bson.M{"userId": "persona-2"}, 1)
	assertMongoCount(t, "conversation_user_states", bson.M{"userId": "persona-2"}, 1)
	assertMongoCount(t, "gathering_membership_projection_states", bson.M{"userId": "persona-2", "sourceVersion": int64(20)}, 1)
	assertMongoCount(t, "conversation_memberships_outbox", bson.M{"eventType": "ConversationMemberAdded"}, 1)
	assertMongoCount(t, "conversations_outbox", bson.M{"eventType": "ConversationRosterUpdated"}, 1)
	stored, err = chatStore.FindConversationByID(ctx, conversation.ID)
	if err != nil || stored.MemberCount != 2 || stored.MembersRosterRevision != 2 {
		t.Fatalf("joined roster drift: value=%+v err=%v", stored, err)
	}

	if _, err := facade.Project(ctx, command); err != nil {
		t.Fatalf("idempotent replay: %v", err)
	}
	assertMongoCount(t, "conversation_memberships_outbox", bson.M{}, 1)
	assertMongoCount(t, "conversations_outbox", bson.M{}, 1)

	organizer := command
	organizer.SourceEventID = "gathering-api:organizer:persona-2:30"
	organizer.SourceVersion = 30
	organizer.SourceType = membershipapp.GatheringProjectionSourceOrganizerAssignment
	if result, err := facade.Project(ctx, organizer); err != nil {
		t.Fatalf("project organizer: %v", err)
	} else if result.AccessRole != membershipapp.GatheringAccessRoleAdmin {
		t.Fatalf("organizer role=%s want admin", result.AccessRole)
	}
	assertMongoCount(t, "conversation_memberships", bson.M{"userId": "persona-2", "role": "admin"}, 1)

	blocked := command
	blocked.SourceEventID = "gathering-api:block:persona-2:40"
	blocked.SourceVersion = 40
	blocked.SourceType = membershipapp.GatheringProjectionSourceBlock
	blocked.State = membershipapp.GatheringProjectionStateBlocked
	if result, err := facade.Project(ctx, blocked); err != nil {
		t.Fatalf("project Block: %v", err)
	} else if result.AccessStatus != membershipapp.GatheringAccessStatusRevoked {
		t.Fatalf("Block access=%s want revoked", result.AccessStatus)
	}
	assertMongoCount(t, "conversation_memberships", bson.M{"userId": "persona-2"}, 0)
	assertMongoCount(t, "conversation_user_states", bson.M{"userId": "persona-2"}, 0)
	assertMongoCount(t, "gathering_membership_projection_states", bson.M{
		"userId": "persona-2", "sources.block.sourceVersion": int64(40), "sources.block.state": "blocked",
	}, 1)

	staleParticipation := command
	staleParticipation.SourceEventID = "gathering-api:participation:persona-2:10"
	staleParticipation.SourceVersion = 10
	if _, err := facade.Project(ctx, staleParticipation); err != nil {
		t.Fatalf("stale Participation must be no-op: %v", err)
	}
	assertMongoCount(t, "conversation_memberships", bson.M{"userId": "persona-2"}, 0)
}

func assertMongoCount(t *testing.T, collection string, filter bson.M, want int64) {
	t.Helper()
	count, err := membershipMongoDatabase.Collection(collection).CountDocuments(context.Background(), filter)
	if err != nil || count != want {
		t.Fatalf("%s count=%d want=%d filter=%v err=%v", collection, count, want, filter, err)
	}
}
