package http

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
)

type createOutboundShareRequest struct {
	Channel           string    `json:"channel"`
	DestinationKind   string    `json:"destinationKind"`
	Destination       string    `json:"destination,omitempty"`
	ReferralID        string    `json:"referralId"`
	DeliverySucceeded bool      `json:"deliverySucceeded"`
	ProviderReceiptID string    `json:"providerReceiptId"`
	ClientConfirmedAt time.Time `json:"clientConfirmedAt"`
}

func (h *ContentHandler) handleCreateOutboundShare(w http.ResponseWriter, r *http.Request) {
	if h.outboundShareService == nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromRequiredDependencyUnavailable("OutboundShareFact facades are not configured"))
		return
	}
	actorDimension, actorID, err := resolveOutboundShareActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var body createOutboundShareRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument("CreateOutboundShare request body is invalid"))
		return
	}
	result, err := h.outboundShareService.AppendOutboundShare(r.Context(), outboundshareapp.AppendOutboundShareCommand{
		PostID: postIDFromPath(r.URL.Path), ActorDimension: actorDimension, ActorID: actorID,
		Channel: body.Channel, DestinationKind: body.DestinationKind, Destination: body.Destination,
		ReferralID: body.ReferralID, DeliverySucceeded: body.DeliverySucceeded,
		ProviderReceiptID: body.ProviderReceiptID, ClientConfirmedAt: body.ClientConfirmedAt,
	})
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusCreated, result)
}

func resolveOutboundShareActor(r *http.Request) (sharemodel.ActorDimension, string, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", "", contentgenerated.AppErrorFromUnauthorized("CreateOutboundShare requires a verified persona or device principal")
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return sharemodel.ActorDimensionPersona, personaID, nil
	}
	if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		return sharemodel.ActorDimensionDevice, deviceActorID, nil
	}
	return "", "", contentgenerated.AppErrorFromUnauthorized("CreateOutboundShare principal has no business actor")
}
