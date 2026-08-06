package http

import (
	"encoding/json"
	"errors"
	nethttp "net/http"
	"strings"

	shared "quwoquan_service/generated/serviceclients/hostauthority"
	rtauth "quwoquan_service/runtime/auth"
	runtimeauthority "quwoquan_service/runtime/hostauthority"
	circlegenerated "quwoquan_service/services/circle-service/generated/circle_management/circle"
	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
)

const internalCirclesPrefix = "/internal/circle/circles/"

func (h *CircleHandler) handleInternalCircleRoute(
	writer nethttp.ResponseWriter,
	request *nethttp.Request,
) {
	remainder := strings.Trim(
		strings.TrimPrefix(request.URL.Path, internalCirclesPrefix),
		"/",
	)
	segments := strings.Split(remainder, "/")
	if request.Method != nethttp.MethodPost ||
		len(segments) != 2 ||
		segments[0] == "" ||
		segments[1] != "gathering-host-authority:evaluate" ||
		h.hostAuthority == nil {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromInvalidArgument("invalid Circle Host authority route"),
		)
		return
	}
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || principal.Subject != "service:circle-service" {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromPermissionDenied(
				"only circle-service may evaluate Circle Host authority",
			),
		)
		return
	}
	var input shared.EvaluationQuery
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromInvalidArgument(
				"decode Circle Host authority query: "+err.Error(),
			),
		)
		return
	}
	circleID := strings.TrimSpace(segments[0])
	if circleID != strings.TrimSpace(input.HostSubjectID) {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromInvalidArgument(
				"Circle path and hostSubjectId mismatch",
			),
		)
		return
	}
	evidence, err := h.hostAuthority.Evaluate(
		request.Context(),
		circleRuntimeQuery(input),
	)
	if errors.Is(err, application.ErrHostAuthoritySubjectNotFound) {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromCircleNotFound(
				"Circle Host authority subject not found",
			),
		)
		return
	}
	if err != nil {
		writeHTTPError(
			writer,
			request,
			circlegenerated.AppErrorFromInternalError(
				"evaluate Circle Host authority: "+err.Error(),
			),
		)
		return
	}
	writeJSON(writer, nethttp.StatusOK, circleEvidence(evidence))
}

func circleRuntimeQuery(input shared.EvaluationQuery) runtimeauthority.Query {
	return runtimeauthority.Query{
		HostSubjectKind: input.HostSubjectKind, HostSubjectID: input.HostSubjectID,
		HostSubjectRef: input.HostSubjectRef, ActorPersonaID: input.ActorPersonaID,
		OrganizerPersonaID:   input.OrganizerPersonaID,
		AuthorityEvidenceRef: input.AuthorityEvidenceRef,
		AuthorityVersion:     input.AuthorityVersion, Action: input.Action,
	}
}

func circleEvidence(input runtimeauthority.Evidence) shared.Evidence {
	return shared.Evidence{
		HostSubjectKind: input.HostSubjectKind, HostSubjectID: input.HostSubjectID,
		HostSubjectRef: input.HostSubjectRef, ActorPersonaID: input.ActorPersonaID,
		OrganizerPersonaID:   input.OrganizerPersonaID,
		AuthorityEvidenceRef: input.AuthorityEvidenceRef,
		AuthorityVersion:     input.AuthorityVersion, AuthorityDigest: input.AuthorityDigest,
		ExpiresAt: input.ExpiresAt, Action: input.Action,
		Valid: input.Valid, Revoked: input.Revoked,
	}
}
