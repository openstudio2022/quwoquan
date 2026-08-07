package http

import (
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	outboundshareapp "quwoquan_service/services/content-service/internal/content/outbound_share_fact/application/command"
	sharemodel "quwoquan_service/services/content-service/internal/content/outbound_share_fact/domain/model"
)

type Handler struct {
	facades *outboundshareapp.Facades
}

func NewHandler(facades *outboundshareapp.Facades) *Handler {
	if facades == nil {
		panic("OutboundShareFact HTTP Handler requires object facades")
	}
	return &Handler{facades: facades}
}

type createOutboundShareRequest struct {
	Channel           sharemodel.Channel         `json:"channel"`
	DestinationKind   sharemodel.DestinationKind `json:"destinationKind"`
	Destination       string                     `json:"destination,omitempty"`
	ReferralID        string                     `json:"referralId"`
	DeliverySucceeded bool                       `json:"deliverySucceeded"`
	ProviderReceiptID string                     `json:"providerReceiptId"`
	ClientConfirmedAt time.Time                  `json:"clientConfirmedAt"`
}

func (handler *Handler) AppendOutboundShareFact(w http.ResponseWriter, r *http.Request) {
	actorDimension, actorID, err := resolveOutboundShareActor(r)
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	var body createOutboundShareRequest
	if err := httpcodec.DecodeStrictJSON(r, &body); err != nil {
		writeHTTPError(w, r, contentgenerated.AppErrorFromInvalidArgument("AppendOutboundShareFact request body is invalid"))
		return
	}
	result, err := handler.facades.AppendOutboundShare(r.Context(), outboundshareapp.AppendOutboundShareCommand{
		PostID: postIDFromRequest(r), ActorDimension: actorDimension, ActorID: actorID,
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

func postIDFromRequest(request *http.Request) string {
	if value := strings.TrimSpace(request.PathValue("postId")); value != "" {
		return value
	}
	parts := strings.Split(strings.Trim(request.URL.Path, "/"), "/")
	for index, part := range parts {
		if part == "posts" && index+1 < len(parts) {
			return strings.TrimSpace(parts[index+1])
		}
	}
	return ""
}

func writeJSON(writer http.ResponseWriter, status int, payload any) {
	httpcodec.WriteJSON(writer, status, payload, "outbound_share_fact")
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

func resolveOutboundShareActor(r *http.Request) (sharemodel.ActorDimension, string, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", "", contentgenerated.AppErrorFromUnauthorized("AppendOutboundShareFact requires a verified persona or device principal")
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return sharemodel.ActorDimensionPersona, personaID, nil
	}
	if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		return sharemodel.ActorDimensionDevice, deviceActorID, nil
	}
	return "", "", contentgenerated.AppErrorFromUnauthorized("AppendOutboundShareFact principal has no business actor")
}
