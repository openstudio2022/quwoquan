package mq

import (
	"context"
	"strings"
)

// RecipientLister 返回会话当前应收到实时事件的成员 userId 列表。
// 由 composition root 用 application.MemberStore 适配注入，避免 mq → application
// 的反向依赖。
type RecipientLister func(ctx context.Context, conversationID string) ([]string, error)

// MemberRecipientResolver 把会话事件接收者解析为去重后的活跃成员 userId。
type MemberRecipientResolver struct {
	list RecipientLister
}

func NewMemberRecipientResolver(list RecipientLister) *MemberRecipientResolver {
	if list == nil {
		panic("chat recipient resolver requires a recipient lister")
	}
	return &MemberRecipientResolver{list: list}
}

func (r *MemberRecipientResolver) ResolveRecipients(
	ctx context.Context,
	conversationID string,
) ([]string, error) {
	ids, err := r.list(ctx, conversationID)
	if err != nil {
		return nil, err
	}
	recipients := make([]string, 0, len(ids))
	seen := make(map[string]struct{}, len(ids))
	for _, raw := range ids {
		userID := strings.TrimSpace(raw)
		if userID == "" {
			continue
		}
		if _, ok := seen[userID]; ok {
			continue
		}
		seen[userID] = struct{}{}
		recipients = append(recipients, userID)
	}
	return recipients, nil
}
