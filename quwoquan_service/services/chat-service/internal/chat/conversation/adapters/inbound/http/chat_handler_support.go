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

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/generated/chat/conversation"
	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

func resolveUserID(r *http.Request) string {
	if r != nil {
		if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
			return strings.TrimSpace(principal.Actor.AccountID)
		}
	}
	return strings.TrimSpace(r.Header.Get("X-Client-User-Id"))
}

// resolvePersonaID returns the verified business actor injected by the shared
// bearer middleware. Message ownership is persona-scoped: using the owner ID
// here makes a message writable by a different identity than the one recorded
// by SendMessage.
func resolvePersonaID(r *http.Request) string {
	if r != nil {
		if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
			return strings.TrimSpace(principal.Actor.PersonaID)
		}
	}
	return strings.TrimSpace(r.Header.Get("X-Client-Persona-Id"))
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

func conversationMemberToWire(
	member model.ConversationMember,
	currentUserID string,
) map[string]any {
	return map[string]any{
		"userId":        member.UserId,
		"userHandle":    strings.TrimSpace(member.UserHandle),
		"displayName":   member.DisplayName,
		"avatarUrl":     member.AvatarUrl,
		"role":          member.Role,
		"memberType":    member.MemberType,
		"joinedAt":      formatOptionalTime(member.JoinedAt),
		"isCurrentUser": member.UserId == currentUserID,
	}
}

func (h *ChatHandler) inboxItemToWire(ctx context.Context, item application.InboxItem) map[string]any {
	conv := item.Conversation
	lastMessageType := strings.TrimSpace(conv.LastMessageType)
	if lastMessageType == "" {
		lastMessageType = "text"
	}
	return map[string]any{
		"id":                 conv.ID,
		"type":               conv.Type,
		"title":              conv.Title,
		"avatarUrl":          h.resolveConversationAvatarURL(ctx, conv),
		"groupAvatarVersion": conv.GroupAvatarVersion,
		"lastMessagePreview": conv.LastMessagePreview,
		"lastMessageType":    lastMessageType,
		"lastMessageTime":    conv.LastMessageTime,
		"lastSeq":            conv.MaxSeq,
		"unreadCount":        item.UserState.UnreadCount,
		"mentionUnreadCount": item.UserState.MentionUnreadCount,
		"muted":              item.UserState.Muted,
		"pinned":             item.UserState.Pinned,
		"circleId":           conv.CircleId,
	}
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

func contactHomeUserRowToWire(
	contact map[string]any,
	intersections []application.ContactIntersectionSummary,
) map[string]any {
	userID := stringFromMap(contact, "userId")
	displayName := stringFromMap(contact, "displayName")
	lastInteraction := stringFromMap(contact, "lastInteraction")
	return map[string]any{
		"id":             userID,
		"kind":           "user",
		"objectId":       userID,
		"userId":         userID,
		"userHandle":     stringFromMap(contact, "userHandle"),
		"conversationId": stringFromMap(contact, "conversationId"),
		"title":          displayName,
		// 用户行的解释只来自服务端 typed intersection summary。个人简介、
		// metFrom 或最近互动时间都不是可证明的交集，不能作为替代文案。
		"subtitle":             "",
		"avatarUrl":            stringFromMap(contact, "avatarUrl"),
		"relationState":        stringFromMap(contact, "relationState"),
		"summaryIntersections": application.ContactIntersectionTexts(intersections),
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
		"userHandle":           "",
		"circleId":             circleID,
		"title":                strings.TrimSpace(hit.DisplayName),
		"subtitle":             strings.TrimSpace(hit.Subtitle),
		"avatarUrl":            strings.TrimSpace(hit.AvatarURL),
		"summaryIntersections": []string{},
		"sortKey":              circleID,
	}
}

func (h *ChatHandler) contactHomeGroupRowToWire(ctx context.Context, conv model.Conversation) map[string]any {
	return map[string]any{
		"id":                   conv.ID,
		"kind":                 "group",
		"objectId":             conv.ID,
		"userHandle":           "",
		"conversationId":       conv.ID,
		"circleId":             conv.CircleId,
		"circleGroupId":        conv.CircleGroupId,
		"entityId":             conv.EntityId,
		"title":                conv.Title,
		"subtitle":             "",
		"avatarUrl":            h.resolveConversationAvatarURL(ctx, conv),
		"summaryIntersections": []string{},
		"sourceEntityTitle":    "",
		"sourceCircleTitle":    "",
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
	canDissolve := role == "owner" && !application.IsManagedConversation(conv)
	return map[string]any{
		"conversationId":     conv.ID,
		"title":              conv.Title,
		"avatarUrl":          h.resolveConversationAvatarURL(ctx, conv),
		"groupAvatarVersion": conv.GroupAvatarVersion,
		"circleId":           conv.CircleId,
		"circleGroupId":      conv.CircleGroupId,
		"gatheringId":        conv.GatheringId,
		"accessMode":         application.EffectiveConversationAccessMode(conv),
		"postingPolicy":      application.EffectiveConversationPostingPolicy(conv),
		"entityId":           conv.EntityId,
		"sourceEntityTitle":  conv.EntityId,
		"sourceCircleTitle":  conv.CircleId,
		"memberCount":        conv.MemberCount,
		"announcement":       conv.Announcement,
		"capabilities":       []string{"album", "file", "event", "member"},
		"originType":         conv.OriginType,
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
	lastMessageType := strings.TrimSpace(conv.LastMessageType)
	if lastMessageType == "" {
		lastMessageType = "text"
	}
	wire := map[string]any{
		"id":                         conv.ID,
		"conversationId":             conv.ID,
		"type":                       conv.Type,
		"title":                      conv.Title,
		"avatarUrl":                  avatarURL,
		"groupAvatarVersion":         conv.GroupAvatarVersion,
		"creatorId":                  conv.CreatorId,
		"circleId":                   conv.CircleId,
		"circleGroupId":              conv.CircleGroupId,
		"gatheringId":                conv.GatheringId,
		"gatheringSourceVersion":     conv.GatheringSourceVersion,
		"gatheringSourceEventId":     conv.GatheringSourceEventID,
		"accessMode":                 application.EffectiveConversationAccessMode(conv),
		"postingPolicy":              application.EffectiveConversationPostingPolicy(conv),
		"entityId":                   conv.EntityId,
		"originType":                 conv.OriginType,
		"originIntersectionSnapshot": conv.OriginIntersectionSnapshot,
		"maxSeq":                     conv.MaxSeq,
		"memberCount":                conv.MemberCount,
		"membersRosterRevision":      conv.MembersRosterRevision,
		"maxGroupSize":               conv.MaxGroupSize,
		"receiptEnabled":             conv.ReceiptEnabled,
		"announcement":               conv.Announcement,
		"announcementUpdatedBy":      conv.AnnouncementUpdatedBy,
		"nameEditableByAdminOnly":    conv.NameEditableByAdminOnly,
		"lastMessageId":              conv.LastMessageId,
		"lastMessagePreview":         conv.LastMessagePreview,
		"lastMessageType":            lastMessageType,
		"lastMessageTime":            conv.LastMessageTime,
		"messageCount":               conv.MessageCount,
		"status":                     conv.Status,
		"createdAt":                  conv.CreatedAt,
		"updatedAt":                  conv.UpdatedAt,
	}
	if conv.AnnouncementUpdatedAt != nil {
		wire["announcementUpdatedAt"] = conv.AnnouncementUpdatedAt.UTC().Format(time.RFC3339Nano)
	}
	return wire
}

func formatOptionalTime(value time.Time) any {
	if value.IsZero() {
		return nil
	}
	return value.UTC().Format(time.RFC3339Nano)
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

func messageToWire(slice application.MessageSlice) map[string]any {
	msg := slice.Message
	wire := map[string]any{
		"id":               msg.ID,
		"conversationId":   msg.ConversationID,
		"seq":              msg.Seq,
		"clientMsgId":      msg.ClientMessageID,
		"senderId":         msg.SenderID,
		"senderName":       msg.SenderDisplayNameSnapshot,
		"senderAvatar":     msg.SenderAvatarURLSnapshot,
		"type":             msg.Type,
		"content":          msg.Content,
		"mediaAssetId":     msg.MediaAssetID,
		"card":             msg.Card,
		"replyToMessageId": msg.ReplyToMessageID,
		"mentions":         msg.Mentions,
		"status":           msg.Status,
		"timestamp":        msg.Timestamp,
	}
	if slice.Media != nil {
		wire["mediaDeliveryUrl"] = slice.Media.DeliveryURL
		wire["mediaType"] = slice.Media.MediaType
		wire["mediaContentType"] = slice.Media.ContentType
		wire["mediaFileSizeBytes"] = slice.Media.FileSize
	}
	if msg.RecalledAt != nil {
		wire["recalledAt"] = msg.RecalledAt
	}
	return wire
}

func writeHTTPError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func newNotFound(entity, id string) *rterr.AppError {
	return generated.AppErrorFromConversationNotFound(entity + " not found: " + id)
}

func readJSON(r *http.Request, v any) error {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		return err
	}
	return json.Unmarshal(body, v)
}

func readStrictJSON(r *http.Request, v any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(v); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return fmt.Errorf("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
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
