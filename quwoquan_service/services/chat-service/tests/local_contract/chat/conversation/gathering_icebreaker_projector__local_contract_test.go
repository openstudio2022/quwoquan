// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/spec.md#sit-004
//
// 活动群一次性破冰卡投影（SIT-004 逐子句）：
//   - 有可展示交集：成员真实新增后下发一张 intersection_icebreaker card
//     消息（主句 ≤2 条、Chat 不拼句），且只下发一次；
//   - 重放收敛：同一成员的重复触发经幂等 messageID 收敛为 no-op，不重复；
//   - 无交集不占位：recommendation 读面无主句时不产生任何消息；
//   - 解析失败不阻断：读面失败只记录，不产生消息也不向成员投影传播失败。
package local_contract

import (
	"context"
	"errors"
	"log/slog"
	"testing"

	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

func icebreakerJoinedFact() membershipapp.GatheringMemberJoinedFact {
	return membershipapp.GatheringMemberJoinedFact{
		SourceEventID:  "gathering-1:participation:persona-new:20",
		GatheringID:    "gathering-1",
		ConversationID: "conversation-1",
		PersonaID:      "persona-new",
		DisplayName:    "新同行者",
	}
}

func newIcebreakerFixture(
	t *testing.T,
	resolver ContactIntersectionResolver,
) (*GatheringIcebreakerProjector, *icebreakerMessageStore, *rtcCallLogProjectionStub) {
	t.Helper()
	messages := &icebreakerMessageStore{}
	projection := &rtcCallLogProjectionStub{}
	service := NewMessageService(
		ChatStoragePorts{
			Messages:          messages,
			MessageProjection: projection,
			Members: icebreakerMemberStore{members: []conversationmodel.ConversationMember{
				{UserId: "persona-old-1", MemberType: "user", DisplayName: "老成员一"},
				{UserId: "persona-new", MemberType: "user", DisplayName: "新同行者"},
				{UserId: "assistant", MemberType: "assistant", DisplayName: "小趣"},
				{UserId: "persona-old-2", MemberType: "user", DisplayName: "老成员二"},
			}},
		},
		&rtcCallLogCacheStub{},
		syncNoopEventPublisher{},
		nil,
		rtcCallLogMediaAssetReader{},
	)
	projector, err := NewGatheringIcebreakerProjector(service, resolver, slog.Default())
	if err != nil {
		t.Fatalf("construct icebreaker projector: %v", err)
	}
	return projector, messages, projection
}

func TestGatheringIcebreakerCardCreatedOnceWithIntersections(t *testing.T) {
	resolver := &recordingIntersectionResolver{
		summariesByContact: map[string][]ContactIntersectionSummary{
			"persona-old-1": {{
				IntersectionID: "int-1",
				SourceRef:      "coWishlistedEntity",
				Dimension:      "wishlist",
				PrimaryText:    "你们都想去贡嘎雪山",
			}},
			"persona-old-2": {{
				IntersectionID: "int-2",
				SourceRef:      "coExperiencedGathering",
				Dimension:      "experience",
				PrimaryText:    "你们都参加过城市观星夜",
			}},
		},
	}
	projector, messages, projection := newIcebreakerFixture(t, resolver)

	projector.OnGatheringMemberJoined(context.Background(), icebreakerJoinedFact())

	if len(messages.commits) != 1 {
		t.Fatalf("expected exactly one icebreaker commit, got %d", len(messages.commits))
	}
	message := messages.commits[0].Message
	if message.Type != "card" || message.Card == nil ||
		message.Card.Kind != messagemodel.MessageCardKindIntersectionIcebreaker {
		t.Fatalf("unexpected icebreaker message: %#v", message)
	}
	if message.Card.Title != "你们都想去贡嘎雪山" ||
		message.Card.Subtitle != "你们都参加过城市观星夜" {
		t.Fatalf(
			"icebreaker must carry resolver primary texts verbatim: title=%q subtitle=%q",
			message.Card.Title,
			message.Card.Subtitle,
		)
	}
	if message.ClientMessageID != "gathering-icebreaker:gathering-1:persona-new" {
		t.Fatalf("icebreaker client message id drifted: %q", message.ClientMessageID)
	}
	if projection.message.ID != message.ID {
		t.Fatalf("icebreaker was not projected: %#v", projection.message)
	}
	// 新成员自身与 assistant 成员不参与配对解析。
	if resolver.calls["persona-new"] != 0 || resolver.calls["assistant"] != 0 {
		t.Fatalf("resolver must not pair new member or assistant: %+v", resolver.calls)
	}

	// 重放：同一成员再次触发，幂等冲突收敛为 no-op，不出现第二张卡。
	messages.conflictOnDuplicate = true
	projector.OnGatheringMemberJoined(context.Background(), icebreakerJoinedFact())
	if len(messages.commits) != 2 || messages.duplicateConflicts != 1 {
		t.Fatalf(
			"replay must converge by idempotent message id: commits=%d conflicts=%d",
			len(messages.commits),
			messages.duplicateConflicts,
		)
	}
	if projection.projections != 1 {
		t.Fatalf("replay must not project a second card: projections=%d", projection.projections)
	}
}

func TestGatheringIcebreakerNoIntersectionProducesNoCard(t *testing.T) {
	projector, messages, projection := newIcebreakerFixture(
		t,
		&recordingIntersectionResolver{},
	)
	projector.OnGatheringMemberJoined(context.Background(), icebreakerJoinedFact())
	if len(messages.commits) != 0 || projection.projections != 0 {
		t.Fatalf(
			"no intersection must not produce a card: commits=%d projections=%d",
			len(messages.commits),
			projection.projections,
		)
	}
}

func TestGatheringIcebreakerResolverFailureDoesNotProduceCard(t *testing.T) {
	projector, messages, _ := newIcebreakerFixture(
		t,
		&recordingIntersectionResolver{err: errors.New("recommendation read plane unavailable")},
	)
	// hook 语义：失败在投影器内部消化，不允许 panic 或向调用方传播。
	projector.OnGatheringMemberJoined(context.Background(), icebreakerJoinedFact())
	if len(messages.commits) != 0 {
		t.Fatalf("resolver failure must not produce a card: commits=%d", len(messages.commits))
	}
}

type recordingIntersectionResolver struct {
	summariesByContact map[string][]ContactIntersectionSummary
	err                error
	calls              map[string]int
}

func (r *recordingIntersectionResolver) ListContactIntersections(
	_ context.Context,
	_ string,
	contactPersonaID string,
	_ int,
) ([]ContactIntersectionSummary, error) {
	if r.calls == nil {
		r.calls = map[string]int{}
	}
	r.calls[contactPersonaID]++
	if r.err != nil {
		return nil, r.err
	}
	return r.summariesByContact[contactPersonaID], nil
}

// icebreakerMemberStore 只实现投影器消费的 ListMembers；其余 MemberStore
// 能力经嵌入接口保持未实现（调用即 panic，测试即失败暴露越权依赖）。
type icebreakerMemberStore struct {
	MemberStore
	members []conversationmodel.ConversationMember
}

func (s icebreakerMemberStore) ListMembers(
	context.Context,
	string,
	ListMembersQuery,
) ([]conversationmodel.ConversationMember, error) {
	return s.members, nil
}

type icebreakerMessageStore struct {
	rtcCallLogMessageStoreStub
	commits             []MessageCommit
	conflictOnDuplicate bool
	duplicateConflicts  int
}

func (s *icebreakerMessageStore) CommitMessage(
	ctx context.Context,
	commit MessageCommit,
) (MessageCommitResult, error) {
	s.commits = append(s.commits, commit)
	if s.conflictOnDuplicate {
		for _, previous := range s.commits[:len(s.commits)-1] {
			if previous.Message.ID == commit.Message.ID {
				s.duplicateConflicts++
				return MessageCommitResult{}, messagemodel.ErrMessageIdempotencyConflict
			}
		}
	}
	return MessageCommitResult{Message: commit.Message, Events: commit.Events}, nil
}
