package http

import (
	"net/http"
	"strings"
	"time"

	"quwoquan_service/generated/serviceclients"
	rterr "quwoquan_service/runtime/errors"
	conversationapp "quwoquan_service/services/chat-service/internal/chat/conversation/application"
)

type assistantGroundingMessageWire struct {
	ID                        string    `json:"id"`
	Seq                       int64     `json:"seq"`
	SenderID                  string    `json:"senderId"`
	SenderDisplayNameSnapshot string    `json:"senderDisplayNameSnapshot"`
	Type                      string    `json:"type"`
	Content                   string    `json:"content"`
	Mentions                  []string  `json:"mentions"`
	Timestamp                 time.Time `json:"timestamp"`
}

type assistantGroundingMessagesResponse struct {
	Items []assistantGroundingMessageWire `json:"items"`
}

func (h *ChatHandler) handleResolveAssistantDeliveryMembership(
	w http.ResponseWriter,
	r *http.Request,
) {
	conversationID := extractPathParam(
		r.URL.Path,
		serviceclients.ChatResolveAssistantDeliveryMembershipPathTemplate,
		"conversationId",
	)
	view, err := h.membershipUseCases.ResolveAssistantDeliveryMembership(
		r.Context(),
		conversationID,
		r.URL.Query().Get("creatorPersonaId"),
		r.URL.Query().Get("assistantMemberId"),
		r.URL.Query().Get("assistantSkillId"),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *ChatHandler) handleListAssistantGroundingMessages(
	w http.ResponseWriter,
	r *http.Request,
) {
	conversationID := extractPathParam(
		r.URL.Path,
		serviceclients.ChatListAssistantGroundingMessagesPathTemplate,
		"conversationId",
	)
	messages, err := h.messageUseCases.ListAssistantGrounding(
		r.Context(),
		conversationID,
		r.URL.Query().Get("creatorPersonaId"),
		r.URL.Query().Get("assistantSkillId"),
		queryInt64(r, "beforeSeq", 0),
		queryInt(r, "limit", 20),
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	items := make([]assistantGroundingMessageWire, 0, len(messages))
	for i := range messages {
		message := messages[i].Message
		items = append(items, assistantGroundingMessageWire{
			ID:                        message.ID,
			Seq:                       message.Seq,
			SenderID:                  message.SenderID,
			SenderDisplayNameSnapshot: message.SenderDisplayNameSnapshot,
			Type:                      message.Type,
			Content:                   message.Content,
			Mentions:                  message.Mentions,
			Timestamp:                 message.Timestamp,
		})
	}
	writeJSON(
		w,
		http.StatusOK,
		assistantGroundingMessagesResponse{Items: items},
	)
}

func (h *ChatHandler) handleSendAssistantDeliveryMessage(
	w http.ResponseWriter,
	r *http.Request,
) {
	conversationID := extractPathParam(
		r.URL.Path,
		serviceclients.ChatSendAssistantDeliveryMessagePathTemplate,
		"conversationId",
	)
	var body struct {
		Type        string `json:"type"`
		Content     string `json:"content"`
		ClientMsgID string `json:"clientMsgId"`
	}
	if err := readStrictJSON(r, &body); err != nil {
		writeHTTPError(
			w,
			r,
			rterr.NewInvalidArgument(
				rterr.ModuleChat,
				"请求体无效",
				err.Error(),
			),
		)
		return
	}
	response, err := h.messageUseCases.SendAssistantDelivery(
		r.Context(),
		conversationapp.AssistantDeliveryMessageRequest{
			ConversationID: conversationID,
			CreatorPersonaID: strings.TrimSpace(
				r.URL.Query().Get("creatorPersonaId"),
			),
			AssistantSkillID: strings.TrimSpace(
				r.URL.Query().Get("assistantSkillId"),
			),
			Type:        strings.TrimSpace(body.Type),
			Content:     body.Content,
			ClientMsgID: strings.TrimSpace(body.ClientMsgID),
		},
	)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, response)
}
