package httpadapter

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rterrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/tag-service/internal/tag/tag_feedback/application/tagfeedback"
	feedbackmodel "quwoquan_service/services/tag-service/internal/tag/tag_feedback/domain/tagfeedback/model"
)

// TagFeedbackHandler 承载 POST /tag/feedback（persona_or_device append 命令）。
type TagFeedbackHandler struct {
	facade *tagfeedback.Facade
}

func NewTagFeedbackHandler(facade *tagfeedback.Facade) *TagFeedbackHandler {
	return &TagFeedbackHandler{facade: facade}
}

func (h *TagFeedbackHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc("POST /tag/feedback", h.handleAppend)
}

func (h *TagFeedbackHandler) handleAppend(w http.ResponseWriter, r *http.Request) {
	var body struct {
		TagRef  string `json:"tagRef"`
		Action  string `json:"action"`
		Context string `json:"context"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeTagError(w, r, tagInvalidArgument("decode tag feedback body: "+err.Error()))
		return
	}
	actorID, actorKind := feedbackActor(r)
	if actorID == "" {
		writeTagError(w, r, tagInvalidArgument("tag feedback requires a persona or device actor"))
		return
	}
	result, err := h.facade.Append(r.Context(), tagfeedback.AppendCommand{
		ActorID:        actorID,
		ActorKind:      actorKind,
		TagRef:         body.TagRef,
		Action:         body.Action,
		Context:        body.Context,
		IdempotencyKey: strings.TrimSpace(r.Header.Get("Idempotency-Key")),
	})
	if err != nil {
		writeTagError(w, r, mapFeedbackError(err))
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"accepted": result.Accepted})
}

func feedbackActor(r *http.Request) (string, string) {
	if persona := strings.TrimSpace(r.Header.Get("X-Client-Sub-Account-Id")); persona != "" {
		return persona, "persona"
	}
	if user := strings.TrimSpace(r.Header.Get("X-Client-User-Id")); user != "" {
		return user, "persona"
	}
	if device := strings.TrimSpace(r.Header.Get("X-Client-Device-Id")); device != "" {
		return device, "device"
	}
	return "", ""
}

// mapFeedbackError 映射为 tag/tag/tag_feedback/errors.yaml 声明的稳定错误。
func mapFeedbackError(err error) error {
	switch {
	case errors.Is(err, feedbackmodel.ErrInvalidArgument):
		return tagInvalidArgument(err.Error())
	case errors.Is(err, feedbackmodel.ErrInvalidAction):
		return feedbackError("feedback_invalid_action", "标签反馈动作不合法", http.StatusBadRequest, err)
	case errors.Is(err, tagfeedback.ErrTagRefNotFound):
		return tagNotFound(err.Error())
	case errors.Is(err, feedbackmodel.ErrIdempotencyConflict):
		return feedbackError("feedback_idempotency_conflict", "重复反馈与原请求不一致", http.StatusConflict, err)
	default:
		return feedbackError("feedback_storage_failed", "标签反馈暂时无法记录，请稍后重试", http.StatusInternalServerError, err)
	}
}

func feedbackError(reason, userMessage string, status int, err error) error {
	kind := rterrors.KindUser
	if status >= 500 {
		kind = rterrors.KindSystem
	}
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, kind, reason), userMessage, err.Error())
	appErr.HTTPStatus = status
	return appErr
}
