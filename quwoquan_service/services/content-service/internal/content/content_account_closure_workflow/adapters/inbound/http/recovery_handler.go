package http

import (
	"encoding/json"
	"errors"
	"io"
	nethttp "net/http"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/content-service/generated/content/content_account_closure_workflow"
	closureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
)

type recoveryRequest struct {
	SourceStreamID string `json:"sourceStreamId"`
}

type Handler struct {
	commands *closureapp.ContentAccountClosureRecoveryCommandFacet
}

func NewHandler(
	commands *closureapp.ContentAccountClosureRecoveryCommandFacet,
) (*Handler, error) {
	if commands == nil {
		return nil, errors.New("content account-closure recovery commands are required")
	}
	return &Handler{commands: commands}, nil
}

// Mount owns the object route while preserving the service composition root's
// existing handler for all other paths.
func (handler *Handler) Mount(base nethttp.Handler) (nethttp.Handler, error) {
	if handler == nil || handler.commands == nil || base == nil {
		return nil, errors.New("content account-closure recovery handler is incomplete")
	}
	mux := nethttp.NewServeMux()
	mux.HandleFunc(
		generated.RouteRecoverContentAccountClosureDeadLetterPath,
		handler.recover,
	)
	mux.Handle("/", base)
	return mux, nil
}

func (handler *Handler) recover(writer nethttp.ResponseWriter, request *nethttp.Request) {
	if request.Method != generated.RouteRecoverContentAccountClosureDeadLetterMethod {
		writer.Header().Set("Allow", generated.RouteRecoverContentAccountClosureDeadLetterMethod)
		handler.writeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleContent,
				"仅支持 POST 恢复请求",
				"content account-closure recovery only accepts POST",
			).WithMetadata("invalid_argument", nethttp.StatusMethodNotAllowed),
		)
		return
	}
	request.Body = nethttp.MaxBytesReader(writer, request.Body, 4096)
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()
	var body recoveryRequest
	if err := decoder.Decode(&body); err != nil || requireEOF(decoder) != nil {
		handler.writeInvalid(writer, request)
		return
	}
	result, err := handler.commands.RecoverAccountClosureDeadLetter(
		request.Context(),
		closureapp.RecoverAccountClosureDeadLetterCommand{
			SourceStreamID: body.SourceStreamID,
			IdempotencyKey: request.Header.Get("Idempotency-Key"),
		},
	)
	if errors.Is(err, closureapp.ErrInvalidDeadLetterRecoveryCommand) {
		handler.writeInvalid(writer, request)
		return
	}
	if err != nil {
		handler.writeError(
			writer,
			request,
			rterr.NewAppError(
				rterr.NewCode(rterr.ModuleContent, rterr.KindSystem, "internal_error"),
				"暂时无法释放待恢复事件",
				"content account-closure terminal marker release failed",
			),
		)
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(nethttp.StatusAccepted)
	_ = json.NewEncoder(writer).Encode(result)
}

func (handler *Handler) writeInvalid(
	writer nethttp.ResponseWriter,
	request *nethttp.Request,
) {
	handler.writeError(
		writer,
		request,
		rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"恢复请求格式无效",
			"content account-closure recovery request is invalid",
		),
	)
}

func (*Handler) writeError(
	writer nethttp.ResponseWriter,
	request *nethttp.Request,
	err *rterr.AppError,
) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

func requireEOF(decoder *json.Decoder) error {
	var trailing any
	err := decoder.Decode(&trailing)
	if errors.Is(err, io.EOF) {
		return nil
	}
	if err == nil {
		return errors.New("unexpected trailing JSON value")
	}
	return err
}
