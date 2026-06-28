package http

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/chat-service/internal/application"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

func resolveUserID(r *http.Request) string {
	return r.Header.Get("X-Client-User-Id")
}

func writeJSON(w http.ResponseWriter, status int, data any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(data)
}

func (h *ChatHandler) flattenConversations(ctx context.Context, convs []model.Conversation) []map[string]any {
	items := make([]map[string]any, 0, len(convs))
	for _, conv := range convs {
		items = append(items, h.conversationToWire(ctx, conv))
	}
	return items
}

func (h *ChatHandler) flattenInboxItems(ctx context.Context, items []application.InboxItem) []map[string]any {
	out := make([]map[string]any, 0, len(items))
	for _, item := range items {
		out = append(out, h.inboxItemToWire(ctx, item))
	}
	return out
}

func (h *ChatHandler) inboxItemToWire(ctx context.Context, item application.InboxItem) map[string]any {
	conv := h.conversationToWire(ctx, item.Conversation)
	conv["lastSeq"] = item.Conversation.MaxSeq
	conv["unreadCount"] = item.UserState.UnreadCount
	conv["mentionUnreadCount"] = item.UserState.MentionUnreadCount
	conv["muted"] = item.UserState.Muted
	conv["pinned"] = item.UserState.Pinned
	return conv
}

func (h *ChatHandler) messageHomeRowToWire(ctx context.Context, item application.InboxItem) map[string]any {
	conv := h.inboxItemToWire(ctx, item)
	return map[string]any{
		"id":                 item.Conversation.ID,
		"kind":               "conversation",
		"conversationId":     item.Conversation.ID,
		"notificationId":     "",
		"conversationType":   item.Conversation.Type,
		"title":              item.Conversation.Title,
		"summary":            item.Conversation.LastMessagePreview,
		"avatarUrl":          conv["avatarUrl"],
		"groupAvatarVersion": item.Conversation.GroupAvatarVersion,
		"lastActiveAt":       item.Conversation.LastMessageTime,
		"unreadCount":        item.UserState.UnreadCount,
		"mentionUnreadCount": item.UserState.MentionUnreadCount,
		"muted":              item.UserState.Muted,
		"pinned":             item.UserState.Pinned,
		"notificationType":   "",
		"read":               item.UserState.UnreadCount == 0,
	}
}

func contactHomeUserRowToWire(contact map[string]any) map[string]any {
	contactID := firstStringFromMap(contact, "contactId", "userId", "id")
	displayName := firstStringFromMap(contact, "displayName", "name")
	metFrom := stringFromMap(contact, "metFrom")
	bio := stringFromMap(contact, "bio")
	lastInteraction := stringFromMap(contact, "lastInteraction")
	return map[string]any{
		"id":                   contactID,
		"kind":                 "user",
		"objectId":             contactID,
		"userId":               contactID,
		"conversationId":       stringFromMap(contact, "conversationId"),
		"title":                displayName,
		"subtitle":             stringFromMap(contact, "subtitle"),
		"avatarUrl":            stringFromMap(contact, "avatarUrl"),
		"relationState":        stringFromMap(contact, "relationState"),
		"summaryIntersections": firstTwoNonEmpty(metFrom, bio),
		"lastActiveAt":         parseOptionalRFC3339(lastInteraction),
		"sortKey":              lastInteraction,
		"isStarred":            boolFromMap(contact, "isStarred"),
	}
}

func contactHomeCircleRowToWire(hit application.ContactHomeCircleHit) map[string]any {
	circleID := strings.TrimSpace(hit.CircleID)
	return map[string]any{
		"id":                   circleID,
		"kind":                 "circle",
		"objectId":             circleID,
		"circleId":             circleID,
		"title":                strings.TrimSpace(hit.DisplayName),
		"subtitle":             strings.TrimSpace(hit.Subtitle),
		"avatarUrl":            strings.TrimSpace(hit.AvatarURL),
		"summaryIntersections": []string{},
		"sortKey":              circleID,
	}
}

func (h *ChatHandler) contactHomeGroupRowToWire(ctx context.Context, conv model.Conversation) map[string]any {
	sourceSummary := joinNonEmpty(" · ", conv.CircleId, conv.EntityId)
	return map[string]any{
		"id":                   conv.ID,
		"kind":                 "group",
		"objectId":             conv.ID,
		"conversationId":       conv.ID,
		"circleId":             conv.CircleId,
		"circleGroupId":        conv.CircleGroupId,
		"entityId":             conv.EntityId,
		"title":                conv.Title,
		"subtitle":             sourceSummary,
		"avatarUrl":            h.resolveConversationAvatarURL(ctx, conv),
		"summaryIntersections": firstTwoNonEmpty(conv.CircleId, conv.EntityId),
		"sourceEntityTitle":    conv.EntityId,
		"sourceCircleTitle":    conv.CircleId,
		"memberCount":          conv.MemberCount,
		"lastActiveAt":         conv.LastMessageTime,
		"sortKey":              conv.LastMessageTime.UTC().Format(time.RFC3339),
	}
}

func (h *ChatHandler) groupHomeToWire(ctx context.Context, conv model.Conversation, userID string) map[string]any {
	role := ""
	if userID != "" && h.memberService != nil {
		if member, err := h.memberService.GetMember(ctx, conv.ID, userID); err == nil {
			role = member.Role
		}
	}
	canManage := role == "owner" || role == "admin"
	canDissolve := role == "owner" && !application.IsCircleBoundConversation(conv)
	return map[string]any{
		"conversationId":     conv.ID,
		"title":              conv.Title,
		"avatarUrl":          h.resolveConversationAvatarURL(ctx, conv),
		"groupAvatarVersion": conv.GroupAvatarVersion,
		"circleId":           conv.CircleId,
		"circleGroupId":      conv.CircleGroupId,
		"entityId":           conv.EntityId,
		"sourceEntityTitle":  conv.EntityId,
		"sourceCircleTitle":  conv.CircleId,
		"memberCount":        conv.MemberCount,
		"announcement":       "",
		"capabilities":       []string{"album", "file", "event", "member"},
		"originType":         conv.OriginType,
		"bindingType":        conv.BindingType,
		"lifecyclePolicy":    conv.LifecyclePolicy,
		"canManageMembers":   canManage,
		"canDissolve":        canDissolve,
	}
}

func normalizeMessageHomeFilter(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "unread", "group", "direct", "notification":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "all"
	}
}

func messageHomeMatchesFilter(item application.InboxItem, filter string) bool {
	switch filter {
	case "unread":
		return item.UserState.UnreadCount > 0
	case "group":
		return item.Conversation.Type == "group"
	case "direct":
		return item.Conversation.Type == "direct" || item.Conversation.Type == "encrypted"
	case "notification":
		return false
	default:
		return true
	}
}

func normalizeContactHomeFilter(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "mutual", "circle", "group":
		return strings.ToLower(strings.TrimSpace(value))
	default:
		return "all"
	}
}

func joinNonEmpty(sep string, values ...string) string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return strings.Join(out, sep)
}

func stringFromMap(m map[string]any, key string) string {
	if m == nil {
		return ""
	}
	value, ok := m[key]
	if !ok || value == nil {
		return ""
	}
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	case []byte:
		return strings.TrimSpace(string(typed))
	default:
		return strings.TrimSpace(fmt.Sprint(value))
	}
}

func firstStringFromMap(m map[string]any, keys ...string) string {
	for _, key := range keys {
		value := stringFromMap(m, key)
		if value != "" {
			return value
		}
	}
	return ""
}

func boolFromMap(m map[string]any, key string) bool {
	if m == nil {
		return false
	}
	value, ok := m[key]
	if !ok {
		return false
	}
	result, ok := value.(bool)
	return ok && result
}

func parseOptionalRFC3339(value string) *time.Time {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return nil
	}
	parsed, err := time.Parse(time.RFC3339, trimmed)
	if err != nil {
		return nil
	}
	return &parsed
}

func (h *ChatHandler) conversationToWire(ctx context.Context, conv model.Conversation) map[string]any {
	avatarURL := h.resolveConversationAvatarURL(ctx, conv)
	return map[string]any{
		"id":                    conv.ID,
		"_id":                   conv.ID,
		"conversationId":        conv.ID,
		"type":                  conv.Type,
		"title":                 conv.Title,
		"avatarUrl":             avatarURL,
		"groupAvatarVersion":    conv.GroupAvatarVersion,
		"creatorId":             conv.CreatorId,
		"circleId":              conv.CircleId,
		"circleGroupId":         conv.CircleGroupId,
		"entityId":              conv.EntityId,
		"originType":            conv.OriginType,
		"bindingType":           conv.BindingType,
		"lifecyclePolicy":       conv.LifecyclePolicy,
		"maxSeq":                conv.MaxSeq,
		"memberCount":           conv.MemberCount,
		"membersRosterRevision": conv.MembersRosterRevision,
		"maxGroupSize":          conv.MaxGroupSize,
		"receiptEnabled":        conv.ReceiptEnabled,
		"lastMessageId":         conv.LastMessageId,
		"lastMessagePreview":    conv.LastMessagePreview,
		"lastMessageTime":       conv.LastMessageTime,
		"messageCount":          conv.MessageCount,
		"status":                conv.Status,
		"createdAt":             conv.CreatedAt,
		"updatedAt":             conv.UpdatedAt,
	}
}

func (h *ChatHandler) resolveConversationAvatarURL(ctx context.Context, conv model.Conversation) string {
	if conv.Type != "group" {
		return application.ResolveConversationAvatarURL(conv)
	}
	if application.ResolveGroupAvatarURL(conv) != "" {
		return application.ResolveConversationAvatarURL(conv)
	}
	if h == nil || h.memberService == nil {
		return application.ResolveConversationAvatarURL(conv)
	}
	members, err := h.memberService.ListMembers(ctx, application.ListMembersRequest{
		ConversationId: conv.ID,
		Limit:          200,
		Sort:           "joined_asc",
	})
	if err != nil {
		return application.ResolveConversationAvatarURL(conv)
	}
	return application.ResolveConversationAvatarURLWithMembers(conv, members)
}

func messageToWire(msg model.Message) map[string]any {
	wire := map[string]any{
		"id":                 msg.ID,
		"_id":                msg.ID,
		"conversationId":     msg.ConversationId,
		"seq":                msg.Seq,
		"clientMsgId":        msg.ClientMsgId,
		"senderId":           msg.SenderId,
		"senderSubAccountId": msg.SenderId,
		"type":               msg.Type,
		"content":            msg.Content,
		"mediaUrl":           msg.MediaUrl,
		"media":              msg.Media,
		"cardPayload":        msg.CardPayload,
		"replyToMessageId":   msg.ReplyToMessageId,
		"mentions":           msg.Mentions,
		"status":             msg.Status,
		"metadata":           msg.Metadata,
		"timestamp":          msg.Timestamp,
	}
	if msg.RecalledAt != nil {
		wire["recalledAt"] = msg.RecalledAt
	}
	if msg.Metadata != nil {
		if displayName, ok := msg.Metadata["senderDisplayNameSnapshot"]; ok {
			wire["senderDisplayNameSnapshot"] = displayName
		}
		if avatarUrl, ok := msg.Metadata["senderAvatarUrlSnapshot"]; ok {
			wire["senderAvatarUrlSnapshot"] = avatarUrl
		}
		if contextVersion, ok := msg.Metadata["personaContextVersion"]; ok {
			wire["personaContextVersion"] = contextVersion
		}
	}
	return wire
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func newNotFound(entity, id string) *rterr.AppError {
	reason := "not_found"
	if entity == "会话" {
		reason = "conversation_not_found"
	}
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleChat, rterr.KindUser, reason),
		entity+"不存在",
		entity+" not found: "+id,
	)
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func queryInt(r *http.Request, key string, defaultVal int) int {
	s := r.URL.Query().Get(key)
	if s == "" {
		return defaultVal
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return defaultVal
	}
	return v
}

func queryInt64(r *http.Request, key string, defaultVal int64) int64 {
	s := r.URL.Query().Get(key)
	if s == "" {
		return defaultVal
	}
	v, err := strconv.ParseInt(s, 10, 64)
	if err != nil {
		return defaultVal
	}
	return v
}
