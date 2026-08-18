package httpadapter

import (
	"encoding/json"
	"net/http"
	"strings"

	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	externalapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

// Handler 只装配 ExternalInteraction 自身的 HTTP 入口，不再承载 Location。
type Handler struct {
	external  *externalapplication.ExternalInteractionService
	readiness *externalapplication.SmsOtpDeliveryReadinessQueryFacade
}

func NewHandler(
	external *externalapplication.ExternalInteractionService,
	readiness ...*externalapplication.SmsOtpDeliveryReadinessQueryFacade,
) *Handler {
	var readinessQueries *externalapplication.SmsOtpDeliveryReadinessQueryFacade
	if len(readiness) > 0 {
		readinessQueries = readiness[0]
	}
	return &Handler{external: external, readiness: readinessQueries}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return mux
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc(
		externalgenerated.SmsOtpDeliveryReadinessPath,
		h.handleSmsOtpDeliveryReadiness,
	)
	mux.HandleFunc(externalgenerated.ExternalRequestsPath, h.handleSubmitExternalRequest)
	mux.HandleFunc(externalgenerated.ExternalRequestDeadLettersPath, h.handleExternalDeadLetters)
	mux.HandleFunc(externalgenerated.ExternalRequestDeadLetterRecoverPath, h.handleRecoverExternalDeadLetter)
	mux.HandleFunc(externalgenerated.ExternalRequestMetricsSnapshotPath, h.handleExternalMetricsSnapshot)
	mux.HandleFunc(externalgenerated.ExternalRequestsPath+"/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/attempts") {
			h.handleExternalAttempts(w, r)
			return
		}
		h.handleGetExternalRequest(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}
