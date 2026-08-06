package http

import (
	"encoding/json"
	"errors"
	nethttp "net/http"
	"strings"

	shared "quwoquan_service/generated/serviceclients/hostauthority"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	runtimeauthority "quwoquan_service/runtime/hostauthority"
	usererrors "quwoquan_service/services/user-service/generated/account/user_account"
	personaerrors "quwoquan_service/services/user-service/generated/persona_management/persona"
	personaapp "quwoquan_service/services/user-service/internal/persona_management/persona/application/persona"
)

type HostAuthorityHandler struct {
	evaluator *personaapp.HostAuthorityEvaluator
}

func NewHostAuthorityHandler(
	evaluator *personaapp.HostAuthorityEvaluator,
) *HostAuthorityHandler {
	if evaluator == nil {
		panic("Persona Host authority handler requires evaluator")
	}
	return &HostAuthorityHandler{evaluator: evaluator}
}

func (handler *HostAuthorityHandler) RegisterRoutes(mux *nethttp.ServeMux) {
	if mux == nil {
		panic("Persona Host authority handler requires HTTP mux")
	}
	mux.HandleFunc(
		"POST /internal/user/personas/{personaId}/gathering-host-authority:evaluate",
		handler.evaluate,
	)
}

func (handler *HostAuthorityHandler) evaluate(
	writer nethttp.ResponseWriter,
	request *nethttp.Request,
) {
	if !isCircleService(request) {
		writeHostAuthorityError(
			writer,
			request,
			usererrors.AppErrorFromUnauthorized("only circle-service may evaluate Persona Host authority"),
		)
		return
	}
	var input shared.EvaluationQuery
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&input); err != nil {
		writeHostAuthorityError(
			writer,
			request,
			usererrors.AppErrorFromInvalidArgument("decode Persona Host authority query: "+err.Error()),
		)
		return
	}
	if strings.TrimSpace(request.PathValue("personaId")) != strings.TrimSpace(input.HostSubjectID) {
		writeHostAuthorityError(
			writer,
			request,
			usererrors.AppErrorFromInvalidArgument("Persona path and hostSubjectId mismatch"),
		)
		return
	}
	evidence, err := handler.evaluator.Evaluate(
		request.Context(),
		toRuntimeQuery(input),
	)
	if errors.Is(err, personaapp.ErrHostAuthoritySubjectNotFound) {
		writeHostAuthorityError(
			writer,
			request,
			personaerrors.AppErrorFromPersonaNotFound("Persona Host authority subject not found"),
		)
		return
	}
	if err != nil {
		writeHostAuthorityError(
			writer,
			request,
			usererrors.AppErrorFromInternalError("evaluate Persona Host authority: "+err.Error()),
		)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(writer).Encode(fromRuntimeEvidence(evidence))
}

func isCircleService(request *nethttp.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	return ok && principal.Subject == "service:circle-service"
}

func toRuntimeQuery(input shared.EvaluationQuery) runtimeauthority.Query {
	return runtimeauthority.Query{
		HostSubjectKind: input.HostSubjectKind, HostSubjectID: input.HostSubjectID,
		HostSubjectRef: input.HostSubjectRef, ActorPersonaID: input.ActorPersonaID,
		OrganizerPersonaID:   input.OrganizerPersonaID,
		AuthorityEvidenceRef: input.AuthorityEvidenceRef,
		AuthorityVersion:     input.AuthorityVersion, Action: input.Action,
	}
}

func fromRuntimeEvidence(input runtimeauthority.Evidence) shared.Evidence {
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

func writeHostAuthorityError(
	writer nethttp.ResponseWriter,
	request *nethttp.Request,
	err *rterr.AppError,
) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}
