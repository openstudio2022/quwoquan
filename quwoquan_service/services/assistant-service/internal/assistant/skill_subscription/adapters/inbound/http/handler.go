package http

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	subscriptionerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_subscription"
	subscriptionapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/application"
	skillmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

const maxRequestBodyBytes = 1 << 20

type Handler struct {
	useCases *subscriptionapplication.UseCases
}

func NewHandler(useCases *subscriptionapplication.UseCases) *Handler {
	return &Handler{useCases: useCases}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /assistant/skill-subscriptions", h.list)
	mux.HandleFunc("POST /assistant/skill-subscriptions", h.create)
	mux.HandleFunc("GET /assistant/skill-subscriptions/{subscriptionId}", h.get)
	mux.HandleFunc("PATCH /assistant/skill-subscriptions/{subscriptionId}/status", h.updateStatus)
	mux.HandleFunc("POST /internal/assistant/skill-subscriptions:tick", h.tick)
}

func (h *Handler) list(w http.ResponseWriter, r *http.Request) {
	accountID, _, err := personaIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	limit := 20
	if raw := strings.TrimSpace(r.URL.Query().Get("limit")); raw != "" {
		if parsed, parseErr := strconv.Atoi(raw); parseErr == nil {
			limit = parsed
		}
	}
	view, err := h.useCases.List(
		r.Context(), accountID,
		strings.TrimSpace(r.URL.Query().Get("status")), limit,
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, view)
}

func (h *Handler) create(w http.ResponseWriter, r *http.Request) {
	accountID, personaID, err := personaIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input skillmodel.CreateSkillSubscriptionInput
	if err := decode(w, r, &input, false); err != nil {
		writeError(w, r, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(err.Error()))
		return
	}
	if err := requireCommandIdentity(r, input.ClientRequestID); err != nil {
		writeError(w, r, err)
		return
	}
	input.CreatedByPersonaID = personaID
	item, err := h.useCases.Create(r.Context(), accountID, input)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, item)
}

func (h *Handler) get(w http.ResponseWriter, r *http.Request) {
	accountID, _, err := personaIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	item, err := h.useCases.Get(r.Context(), accountID, r.PathValue("subscriptionId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (h *Handler) updateStatus(w http.ResponseWriter, r *http.Request) {
	accountID, _, err := personaIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input skillmodel.UpdateSkillSubscriptionStatusInput
	if err := decode(w, r, &input, false); err != nil {
		writeError(w, r, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(err.Error()))
		return
	}
	if err := requireCommandIdentity(r, input.ClientRequestID); err != nil {
		writeError(w, r, err)
		return
	}
	item, err := h.useCases.UpdateStatus(
		r.Context(), accountID, r.PathValue("subscriptionId"), input,
	)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, item)
}

func (h *Handler) tick(w http.ResponseWriter, r *http.Request) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok || strings.TrimSpace(principal.Subject) == "" {
		writeError(w, r, subscriptionerrors.AppErrorFromSubscriptionUnauthorized(
			"trusted service principal is required",
		))
		return
	}
	if err := requireCommandIdentity(r, r.Header.Get("Idempotency-Key")); err != nil {
		writeError(w, r, err)
		return
	}
	var input skillmodel.SkillSubscriptionCronTickInput
	if err := decode(w, r, &input, true); err != nil {
		writeError(w, r, subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(err.Error()))
		return
	}
	result, err := h.useCases.Tick(r.Context(), input)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func personaIdentity(r *http.Request) (string, string, error) {
	if principal, ok := rtauth.PrincipalFromContext(r.Context()); ok {
		accountID := strings.TrimSpace(principal.Actor.AccountID)
		if accountID == "" {
			accountID = strings.TrimSpace(principal.Subject)
		}
		personaID := strings.TrimSpace(principal.Actor.PersonaID)
		if accountID != "" && personaID != "" {
			return accountID, personaID, nil
		}
	}
	return "", "", subscriptionerrors.AppErrorFromSubscriptionUnauthorized(
		"trusted account and persona principal are required",
	)
}

func requireCommandIdentity(r *http.Request, bodyID string) error {
	headerID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	bodyID = strings.TrimSpace(bodyID)
	if headerID == "" || bodyID == "" || headerID != bodyID {
		return subscriptionerrors.AppErrorFromSubscriptionInvalidArgument(
			"Idempotency-Key must be present and match the command identity",
		)
	}
	return nil
}

func decode(w http.ResponseWriter, r *http.Request, value any, allowEmpty bool) error {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBodyBytes))
	decoder.DisallowUnknownFields()
	err := decoder.Decode(value)
	if allowEmpty && err == io.EOF {
		return nil
	}
	return err
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}
