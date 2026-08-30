package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

// requireActiveConversationMember 是所有依赖 ConversationUserState 或成员写操作的
// 单一授权门：非成员统一返回 not_found，已终止会话返回 conversation_dissolved。
func requireActiveConversationMember(
	ctx context.Context,
	conversations ConversationStore,
	members MemberStore,
	conversationID string,
	personaID string,
) (*model.Conversation, *model.ConversationMember, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return nil, nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "unauthorized"),
			"请先登录",
			"conversation membership requires an authenticated persona",
		)
	}
	conv, err := conversations.FindConversationByID(ctx, conversationID)
	if err != nil {
		return nil, nil, err
	}
	member, err := members.FindMember(ctx, conversationID, personaID)
	if err != nil {
		return nil, nil, chatConversationNotFoundForNonMember(
			"persona is not a member of this conversation",
		)
	}
	if conv.Status != model.ConversationStatusActive {
		return nil, nil, chatConversationDissolved("conversation is not active")
	}
	return conv, member, nil
}
