package httpadapter

import (
	"encoding/json"
	"net/http"
	"strings"

	"quwoquan_service/services/notification-service/internal/application"
)

type Handler struct {
	service *application.NotificationDeliveryService
}

func NewHandler(service *application.NotificationDeliveryService) *Handler {
	return &Handler{service: service}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/v1/notifications/delivery/metrics:snapshot", h.handleMetrics)
	mux.HandleFunc("/v1/notifications/dead-letters:recover", h.handleRecover)
	return mux
}

func (h *Handler) handleMetrics(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	snapshot, err := h.service.Metrics(r.Context())
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, snapshot)
}

func (h *Handler) handleRecover(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"error": "method not allowed"})
		return
	}
	body := map[string]string{}
	_ = json.NewDecoder(r.Body).Decode(&body)
	notificationID := strings.TrimSpace(body["notificationId"])
	if notificationID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "notificationId required"})
		return
	}
	if err := h.service.RecoverNotification(r.Context(), notificationID); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusAccepted, map[string]any{"notificationId": notificationID, "recovered": true})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
