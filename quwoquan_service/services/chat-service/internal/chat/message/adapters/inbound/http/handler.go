package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	chatgenerated "quwoquan_service/services/chat-service/generated/chat/conversation"
	messageapp "quwoquan_service/services/chat-service/internal/chat/message/application"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
)

type Handler struct {
	useCases *messageapp.UseCases
}

func NewHandler(backend messageapp.Backend) *Handler {
	return &Handler{useCases: messageapp.NewUseCases(backend)}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("message route mux is required")
	}
	mux.HandleFunc("GET /chat/conversations/{conversationId}/messages", handler.listMessages)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/messages", handler.sendMessage)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/messages/{messageId}/recall", handler.recallMessage)
	mux.HandleFunc("POST /chat/conversations/{conversationId}/sync", handler.syncMessages)
	mux.HandleFunc("GET /internal/chat/conversations/{conversationId}/assistant-grounding-messages", handler.listAssistantGroundingMessages)
	mux.HandleFunc("POST /internal/chat/conversations/{conversationId}/assistant-delivery-messages", handler.sendAssistantDeliveryMessage)
}

func (handler *Handler) listMessages(writer http.ResponseWriter, request *http.Request) {
	limit := queryInt(request, "limit", 20)
	messages, err := handler.useCases.List(request.Context(), messageapp.ListMessagesRequest{
		ConversationId: request.PathValue("conversationId"),
		ViewerID:       personaID(request),
		Limit:          limit + 1,
		AfterSeq:       queryInt64(request, "afterSeq", 0),
		BeforeSeq:      queryInt64(request, "beforeSeq", 0),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	hasNextPage := len(messages) > limit
	if hasNextPage {
		messages = messages[:limit]
	}
	items := make([]map[string]any, 0, len(messages))
	for _, message := range messages {
		items = append(items, messageToWire(message))
	}
	response := map[string]any{"items": items}
	if hasNextPage {
		response["nextBeforeSeq"] = messages[len(messages)-1].Message.Seq
	}
	writeJSON(writer, http.StatusOK, response)
}

func (handler *Handler) sendMessage(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		Type                      string                         `json:"type"`
		Content                   string                         `json:"content"`
		MediaAssetID              string                         `json:"mediaAssetId"`
		AudioDurationMs           int64                          `json:"audioDurationMs"`
		AudioWaveform             []float64                      `json:"audioWaveform"`
		Card                      *messageapp.MessageCardCommand `json:"card"`
		ReplyToMessageID          string                         `json:"replyToMessageId"`
		Mentions                  []string                       `json:"mentions"`
		ClientMessageID           string                         `json:"clientMsgId"`
		PersonaContextVersion     int64                          `json:"personaContextVersion"`
		SenderDisplayNameSnapshot string                         `json:"senderDisplayNameSnapshot"`
		SenderAvatarURLSnapshot   string                         `json:"senderAvatarUrlSnapshot"`
	}
	if err := readStrictJSON(request, &body); err != nil {
		// SendMessage 契约只声明 message_invalid；未知/非法 wire 键按
		// 消息契约违规映射，不得泄漏契约外的 invalid_argument。
		writeError(writer, request, chatgenerated.AppErrorFromMessageInvalid(
			"message wire payload is invalid: "+err.Error(),
		))
		return
	}
	response, err := handler.useCases.Send(request.Context(), messageapp.SendMessageRequest{
		ConversationId:            request.PathValue("conversationId"),
		SenderId:                  personaID(request),
		SenderAccountID:           accountID(request),
		PersonaContextVersion:     body.PersonaContextVersion,
		SenderDisplayNameSnapshot: strings.TrimSpace(body.SenderDisplayNameSnapshot),
		SenderAvatarUrlSnapshot:   strings.TrimSpace(body.SenderAvatarURLSnapshot),
		Type:                      body.Type,
		Content:                   body.Content,
		MediaAssetID:              body.MediaAssetID,
		AudioDurationMs:           body.AudioDurationMs,
		AudioWaveform:             body.AudioWaveform,
		Card:                      body.Card,
		ReplyToMessageId:          body.ReplyToMessageID,
		Mentions:                  body.Mentions,
		ClientMsgId:               body.ClientMessageID,
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusCreated, response)
}

func (handler *Handler) recallMessage(writer http.ResponseWriter, request *http.Request) {
	if err := handler.useCases.Recall(
		request.Context(),
		request.PathValue("conversationId"),
		request.PathValue("messageId"),
		personaID(request),
	); err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusOK, map[string]any{"status": "recalled"})
}

func (handler *Handler) syncMessages(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		LastSeq int64 `json:"lastSeq"`
		Limit   int   `json:"limit"`
	}
	if err := readStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleChat, "同步请求无效", err.Error()))
		return
	}
	response, err := handler.useCases.Sync(request.Context(), messageapp.SyncMessagesRequest{
		ConversationId: request.PathValue("conversationId"),
		ViewerID:       personaID(request),
		LastSeq:        body.LastSeq,
		Limit:          body.Limit,
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	items := make([]map[string]any, 0, len(response.Messages))
	for _, message := range response.Messages {
		items = append(items, messageToWire(message))
	}
	writeJSON(writer, http.StatusOK, map[string]any{
		"messages": items,
		"hasMore":  response.HasMore,
	})
}

type assistantGroundingMessageWire struct {
	ID                        string                    `json:"id"`
	Seq                       int64                     `json:"seq"`
	SenderID                  string                    `json:"senderId"`
	SenderDisplayNameSnapshot string                    `json:"senderDisplayNameSnapshot"`
	Type                      string                    `json:"type"`
	Content                   string                    `json:"content"`
	Mentions                  []string                  `json:"mentions"`
	Timestamp                 time.Time                 `json:"timestamp"`
	Card                      *messagemodel.MessageCard `json:"card,omitempty"`
}

func (handler *Handler) listAssistantGroundingMessages(writer http.ResponseWriter, request *http.Request) {
	messages, err := handler.useCases.ListAssistantGrounding(
		request.Context(),
		request.PathValue("conversationId"),
		request.URL.Query().Get("creatorPersonaId"),
		queryInt64(request, "beforeSeq", 0),
		queryInt(request, "limit", 20),
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	items := make([]assistantGroundingMessageWire, 0, len(messages))
	for _, item := range messages {
		message := item.Message
		items = append(items, assistantGroundingMessageWire{
			ID: message.ID, Seq: message.Seq, SenderID: message.SenderID,
			SenderDisplayNameSnapshot: message.SenderDisplayNameSnapshot,
			Type:                      message.Type, Content: message.Content, Mentions: message.Mentions,
			Timestamp: message.Timestamp, Card: message.Card,
		})
	}
	writeJSON(writer, http.StatusOK, map[string]any{"items": items})
}

func (handler *Handler) sendAssistantDeliveryMessage(writer http.ResponseWriter, request *http.Request) {
	var body struct {
		Type        string `json:"type"`
		Content     string `json:"content"`
		ClientMsgID string `json:"clientMsgId"`
	}
	if err := readStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleChat, "请求体无效", err.Error()))
		return
	}
	response, err := handler.useCases.SendAssistantDelivery(
		request.Context(),
		messageapp.AssistantDeliveryMessageRequest{
			ConversationID:   request.PathValue("conversationId"),
			CreatorPersonaID: strings.TrimSpace(request.URL.Query().Get("creatorPersonaId")),
			Type:             strings.TrimSpace(body.Type), Content: body.Content,
			ClientMsgID: strings.TrimSpace(body.ClientMsgID),
		},
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, http.StatusCreated, response)
}

func messageToWire(slice messageapp.MessageSlice) map[string]any {
	message := slice.Message
	wire := map[string]any{
		"id": message.ID, "conversationId": message.ConversationID, "seq": message.Seq,
		"clientMsgId": message.ClientMessageID, "senderId": message.SenderID,
		"senderName":   message.SenderDisplayNameSnapshot,
		"senderAvatar": message.SenderAvatarURLSnapshot, "type": message.Type,
		"content": message.Content, "mediaAssetId": message.MediaAssetID,
		"card": message.Card, "replyToMessageId": message.ReplyToMessageID,
		"mentions": message.Mentions, "status": message.Status, "timestamp": message.Timestamp,
	}
	if message.AudioDurationMs > 0 {
		wire["audioDurationMs"] = message.AudioDurationMs
	}
	if len(message.AudioWaveform) > 0 {
		wire["audioWaveform"] = message.AudioWaveform
	}
	if slice.Media != nil {
		wire["mediaDeliveryUrl"] = slice.Media.DeliveryURL
		wire["mediaType"] = slice.Media.MediaType
		wire["mediaContentType"] = slice.Media.ContentType
		wire["mediaFileSizeBytes"] = slice.Media.FileSize
	}
	if message.RecalledAt != nil {
		wire["recalledAt"] = message.RecalledAt
	}
	return wire
}

func personaID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.PersonaID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Persona-Id"))
}

func accountID(request *http.Request) string {
	if principal, ok := rtauth.PrincipalFromContext(request.Context()); ok {
		return strings.TrimSpace(principal.Actor.AccountID)
	}
	return strings.TrimSpace(request.Header.Get("X-Client-Account-Id"))
}

func readStrictJSON(request *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		if err == nil {
			return rterr.NewInvalidArgument(rterr.ModuleChat, "请求体无效", "request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
}

func queryInt(request *http.Request, key string, fallback int) int {
	value, err := strconv.Atoi(request.URL.Query().Get(key))
	if err != nil {
		return fallback
	}
	return value
}

func queryInt64(request *http.Request, key string, fallback int64) int64 {
	value, err := strconv.ParseInt(request.URL.Query().Get(key), 10, 64)
	if err != nil {
		return fallback
	}
	return value
}

func writeJSON(writer http.ResponseWriter, statusCode int, value any) {
	writer.Header().Set("Content-Type", "application/json; charset=utf-8")
	writer.WriteHeader(statusCode)
	_ = json.NewEncoder(writer).Encode(value)
}

func writeError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
