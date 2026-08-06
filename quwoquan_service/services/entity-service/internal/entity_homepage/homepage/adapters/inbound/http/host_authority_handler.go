package httpadapter

import (
	"errors"
	"net/http"
	"strings"

	shared "quwoquan_service/generated/serviceclients/hostauthority"
	rtauth "quwoquan_service/runtime/auth"
	runtimeauthority "quwoquan_service/runtime/hostauthority"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
)

const internalHomepagePrefix = "/internal/entity/homepages/"

func (h *Handler) handleInternalHomepageRoute(
	writer http.ResponseWriter,
	request *http.Request,
) {
	remainder := strings.Trim(
		strings.TrimPrefix(request.URL.Path, internalHomepagePrefix),
		"/",
	)
	segments := strings.Split(remainder, "/")
	if len(segments) != 2 ||
		segments[0] == "" ||
		segments[1] != "gathering-host-authority:evaluate" {
		writeRuntimeNotFound(writer, request)
		return
	}
	h.handleGatheringHostAuthority(writer, request, segments[0], segments)
}

func (h *Handler) handleGatheringHostAuthority(
	writer http.ResponseWriter,
	request *http.Request,
	homepageID string,
	segments []string,
) {
	if request.Method != http.MethodPost ||
		len(segments) != 2 ||
		h.hostAuthority == nil {
		writeRuntimeNotFound(writer, request)
		return
	}
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok || principal.Subject != "service:circle-service" {
		writeError(
			writer,
			request,
			entitygenerated.AppErrorFromPermissionDenied(
				"only circle-service may evaluate EntityHomepage Host authority",
			),
		)
		return
	}
	var input shared.EvaluationQuery
	if err := decodeJSON(request, &input); err != nil {
		writeError(
			writer,
			request,
			entitygenerated.AppErrorFromInvalidArgument(
				"decode EntityHomepage Host authority query: "+err.Error(),
			),
		)
		return
	}
	if strings.TrimSpace(homepageID) != strings.TrimSpace(input.HostSubjectID) {
		writeError(
			writer,
			request,
			entitygenerated.AppErrorFromInvalidArgument(
				"EntityHomepage path and hostSubjectId mismatch",
			),
		)
		return
	}
	evidence, err := h.hostAuthority.Evaluate(
		request.Context(),
		entityRuntimeQuery(input),
	)
	if errors.Is(err, homepageapp.ErrHostAuthoritySubjectNotFound) {
		writeError(
			writer,
			request,
			entitygenerated.AppErrorFromHomepageNotFound(
				"EntityHomepage Host authority subject not found",
			),
		)
		return
	}
	if err != nil {
		writeError(
			writer,
			request,
			entitygenerated.AppErrorFromInternalError(
				"evaluate EntityHomepage Host authority: "+err.Error(),
			),
		)
		return
	}
	writeJSON(writer, http.StatusOK, entityEvidence(evidence))
}

func entityRuntimeQuery(input shared.EvaluationQuery) runtimeauthority.Query {
	return runtimeauthority.Query{
		HostSubjectKind: input.HostSubjectKind, HostSubjectID: input.HostSubjectID,
		HostSubjectRef: input.HostSubjectRef, ActorPersonaID: input.ActorPersonaID,
		OrganizerPersonaID:   input.OrganizerPersonaID,
		AuthorityEvidenceRef: input.AuthorityEvidenceRef,
		AuthorityVersion:     input.AuthorityVersion, Action: input.Action,
	}
}

func entityEvidence(input runtimeauthority.Evidence) shared.Evidence {
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
