package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"strings"
	"time"

	messageevent "quwoquan_service/services/chat-service/generated/chat/message/contract/event"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

// icebreakerPairScanLimit 限制交集解析的既有成员数（每人一次 recommendation
// 读面调用），避免大群成员加入时放大远程调用。
const icebreakerPairScanLimit = 5

// icebreakerFactLimit 是破冰卡最多携带的交集主句数（SIT-004：主句 ≤2 条）。
const icebreakerFactLimit = 2

// GatheringIcebreakerProjector 把活动群成员真实新增投影为一次性
// intersection_icebreaker 系统卡：
//   - 交集主句由既有 recommendation 对象交集读面（ContactIntersectionResolver）
//     按「新成员 × 既有成员」解析，Chat 不拼句、不造依据；
//   - 无可展示交集不下发（不占位）；
//   - 幂等：messageID 由 gatheringId+personaId 确定，同一成员重复加入或
//     事件重放不产生第二张卡；
//   - best-effort：解析或写入失败只记录结构化日志，不阻断成员投影主事实。
type GatheringIcebreakerProjector struct {
	messages *MessageService
	resolver ContactIntersectionResolver
	logger   *slog.Logger
}

func NewGatheringIcebreakerProjector(
	messages *MessageService,
	resolver ContactIntersectionResolver,
	logger *slog.Logger,
) (*GatheringIcebreakerProjector, error) {
	if messages == nil || resolver == nil {
		return nil, errors.New(
			"gathering icebreaker projector requires message service and intersection resolver",
		)
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &GatheringIcebreakerProjector{
		messages: messages,
		resolver: resolver,
		logger:   logger,
	}, nil
}

// OnGatheringMemberJoined 实现 membershipapp.GatheringMemberJoinedHook。
func (p *GatheringIcebreakerProjector) OnGatheringMemberJoined(
	ctx context.Context,
	fact membershipapp.GatheringMemberJoinedFact,
) {
	if err := p.project(ctx, fact); err != nil {
		p.logger.WarnContext(
			ctx,
			"gathering icebreaker card projection failed",
			"gathering_id", fact.GatheringID,
			"conversation_id", fact.ConversationID,
			"persona_id", fact.PersonaID,
			"error", err,
		)
	}
}

func (p *GatheringIcebreakerProjector) project(
	ctx context.Context,
	fact membershipapp.GatheringMemberJoinedFact,
) error {
	gatheringID := strings.TrimSpace(fact.GatheringID)
	conversationID := strings.TrimSpace(fact.ConversationID)
	personaID := strings.TrimSpace(fact.PersonaID)
	if gatheringID == "" || conversationID == "" || personaID == "" {
		return errors.New("gathering icebreaker fact is incomplete")
	}
	members, err := p.messages.members.ListMembers(ctx, conversationID, ListMembersQuery{
		Limit: icebreakerPairScanLimit + 2,
	})
	if err != nil {
		return err
	}
	summaries := p.resolvePairIntersections(ctx, personaID, members)
	if len(summaries) == 0 {
		// 无可展示交集不下发、不占位（SIT-004）。
		return nil
	}
	title := summaries[0].primaryText
	subtitle := ""
	if len(summaries) > 1 {
		subtitle = summaries[1].primaryText
	}
	messageID := stableIcebreakerMessageID(gatheringID, personaID)
	now := time.Now().UTC()
	attributes := []messagemodel.MessageCardAttribute{
		{Name: "gatheringId", Value: gatheringID},
		{Name: "newMemberId", Value: personaID},
	}
	for _, summary := range summaries {
		attributes = append(attributes, messagemodel.MessageCardAttribute{
			Name: "pairMemberId:" + summary.intersectionID, Value: summary.pairPersonaID,
		})
	}
	msg := messagemodel.Message{
		ID:              messageID,
		ConversationID:  conversationID,
		ClientMessageID: "gathering-icebreaker:" + gatheringID + ":" + personaID,
		SenderID:        personaID,
		Type:            "card",
		Content:         "",
		Card: &messagemodel.MessageCard{
			Kind:       messagemodel.MessageCardKindIntersectionIcebreaker,
			Title:      title,
			Subtitle:   subtitle,
			Attributes: attributes,
		},
		Status:    "sent",
		Timestamp: now,
		Version:   1,
	}
	digest := sha256.Sum256([]byte(
		"gathering-icebreaker\x00" + gatheringID + "\x00" + personaID +
			"\x00" + title + "\x00" + subtitle,
	))
	committed, err := p.messages.messages.CommitMessage(ctx, MessageCommit{
		Message:       msg,
		CommandDigest: hex.EncodeToString(digest[:]),
		Events: []messageports.OutboxEvent{{
			EventID:        messageID + ":" + messageevent.MessageSent,
			EventType:      messageevent.MessageSent,
			ConversationID: conversationID,
			ActorID:        personaID,
			Payload: map[string]any{
				"conversationId": conversationID,
				"type":           msg.Type,
				"content":        msg.Content,
				"card":           msg.Card,
				"clientMsgId":    msg.ClientMessageID,
				"senderId":       msg.SenderID,
			},
		}},
	})
	if err != nil {
		if errors.Is(err, messagemodel.ErrMessageIdempotencyConflict) {
			// 同一成员的破冰卡已存在：一次性语义收敛，重放为 no-op。
			return nil
		}
		return err
	}
	if err := p.messages.projection.ProjectCommittedMessage(ctx, committed.Message); err != nil {
		return err
	}
	return p.messages.cache.InvalidateConversation(ctx, conversationID)
}

type icebreakerFact struct {
	primaryText    string
	intersectionID string
	pairPersonaID  string
}

// resolvePairIntersections 按「新成员 × 既有成员」调用 recommendation 读面，
// 主句去空去重、最多两条；单个成员的解析失败不中断其余（best-effort）。
func (p *GatheringIcebreakerProjector) resolvePairIntersections(
	ctx context.Context,
	newMemberID string,
	members []conversationmodel.ConversationMember,
) []icebreakerFact {
	facts := make([]icebreakerFact, 0, icebreakerFactLimit)
	seen := map[string]struct{}{}
	scanned := 0
	for _, member := range members {
		if scanned >= icebreakerPairScanLimit || len(facts) >= icebreakerFactLimit {
			break
		}
		if member.MemberType != "user" || member.UserId == newMemberID {
			continue
		}
		scanned++
		summaries, err := p.resolver.ListContactIntersections(
			ctx, newMemberID, member.UserId, icebreakerFactLimit,
		)
		if err != nil {
			p.logger.WarnContext(
				ctx,
				"gathering icebreaker intersection resolution failed",
				"pair_persona_id", member.UserId,
				"error", err,
			)
			continue
		}
		for _, summary := range summaries {
			text := strings.TrimSpace(summary.PrimaryText)
			intersectionID := strings.TrimSpace(summary.IntersectionID)
			if text == "" || intersectionID == "" {
				continue
			}
			if _, exists := seen[text]; exists {
				continue
			}
			seen[text] = struct{}{}
			facts = append(facts, icebreakerFact{
				primaryText:    text,
				intersectionID: intersectionID,
				pairPersonaID:  member.UserId,
			})
			if len(facts) >= icebreakerFactLimit {
				break
			}
		}
	}
	return facts
}

func stableIcebreakerMessageID(gatheringID, personaID string) string {
	sum := sha256.Sum256([]byte("gathering-icebreaker\x00" + gatheringID + "\x00" + personaID))
	return "gathering-icebreaker-" + hex.EncodeToString(sum[:16])
}
