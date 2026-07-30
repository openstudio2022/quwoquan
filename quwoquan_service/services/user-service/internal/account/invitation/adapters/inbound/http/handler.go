package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	usergenerated "quwoquan_service/services/user-service/generated/account/user_account"
	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
)

type Handler struct {
	facade *invitationapp.Facade
}

func NewHandler(facade *invitationapp.Facade) (*Handler, error) {
	if facade == nil {
		return nil, errors.New("invitation facade is required")
	}
	return &Handler{facade: facade}, nil
}

func (handler *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /user/invites", handler.generate)
	mux.HandleFunc("GET /user/invites", handler.list)
	mux.HandleFunc("GET /invites/{linkCode}", handler.getByCode)
	mux.HandleFunc("POST /invites/{linkCode}/accept", handler.accept)
}

func (handler *Handler) generate(w http.ResponseWriter, r *http.Request) {
	actorAccountID := actorAccountID(r)
	if actorAccountID == "" {
		writeError(w, r, usergenerated.AppErrorFromUnauthorized("authenticated account required"))
		return
	}
	body, err := readBody(r)
	if err != nil {
		writeError(w, r, usergenerated.AppErrorFromInvalidArgument("invalid body"))
		return
	}
	inviterPersonaID, _ := body["personaId"].(string)
	channel, _ := body["channel"].(string)
	inviteePhone, _ := body["inviteePhone"].(string)
	record, err := handler.facade.Generate(
		r.Context(),
		actorAccountID,
		inviterPersonaID,
		channel,
		inviteePhone,
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, privateResponse(record))
}

func (handler *Handler) list(w http.ResponseWriter, r *http.Request) {
	actorAccountID := actorAccountID(r)
	if actorAccountID == "" {
		writeError(w, r, usergenerated.AppErrorFromUnauthorized("authenticated account required"))
		return
	}
	limit, err := queryInt(r, "limit", 20)
	if err != nil {
		writeError(w, r, usergenerated.AppErrorFromInvalidArgument("limit must be an integer"))
		return
	}
	offset, err := queryInt(r, "offset", 0)
	if err != nil {
		writeError(w, r, usergenerated.AppErrorFromInvalidArgument("offset must be an integer"))
		return
	}
	records, err := handler.facade.List(
		r.Context(),
		actorAccountID,
		r.URL.Query().Get("personaId"),
		r.URL.Query().Get("status"),
		limit,
		offset,
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	items := make([]map[string]any, 0, len(records))
	for index := range records {
		items = append(items, privateResponse(&records[index]))
	}
	writeJSON(w, http.StatusOK, map[string]any{"invites": items})
}

func (handler *Handler) getByCode(w http.ResponseWriter, r *http.Request) {
	record, err := handler.facade.GetByCode(r.Context(), r.PathValue("linkCode"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, publicResponse(record))
}

func (handler *Handler) accept(w http.ResponseWriter, r *http.Request) {
	actorAccountID := actorAccountID(r)
	if actorAccountID == "" {
		writeError(w, r, usergenerated.AppErrorFromUnauthorized("authenticated account required"))
		return
	}
	record, err := handler.facade.Accept(r.Context(), actorAccountID, r.PathValue("linkCode"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, publicResponse(record))
}

func privateResponse(record *invitationmodel.Invitation) map[string]any {
	response := publicResponse(record)
	if record != nil {
		response["linkCode"] = record.LinkCode
		response["acceptedAt"] = record.AcceptedAt
		response["convertedAt"] = record.ConvertedAt
	}
	return response
}

func publicResponse(record *invitationmodel.Invitation) map[string]any {
	if record == nil {
		return map[string]any{}
	}
	return map[string]any{
		"id":               record.ID,
		"inviterPersonaId": record.InviterPersonaID,
		"channel":          record.Channel,
		"status":           record.Status,
		"expireAt":         record.ExpireAt,
		"generatedAt":      record.GeneratedAt,
	}
}

func actorAccountID(r *http.Request) string {
	current, ok := operation.FromContext(r.Context())
	if !ok {
		return ""
	}
	return strings.TrimSpace(current.Actor.AccountID)
}

func queryInt(r *http.Request, key string, fallback int) (int, error) {
	raw := strings.TrimSpace(r.URL.Query().Get(key))
	if raw == "" {
		return fallback, nil
	}
	return strconv.Atoi(raw)
}

func readBody(r *http.Request) (map[string]any, error) {
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		return nil, err
	}
	return body, nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
