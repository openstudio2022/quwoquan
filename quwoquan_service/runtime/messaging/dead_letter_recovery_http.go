package runtimemessaging

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

// DeadLetterReleaser releases a terminal marker so the consumer can reclaim
// the original source PEL entry. Implementations must never reconstruct an
// event from the sanitized DLQ record.
type DeadLetterReleaser interface {
	RecoverDeadLetter(ctx context.Context, sourceStreamID string) error
}

type DeadLetterRecoveryRouteConfig struct {
	Path     string
	Module   rterr.Module
	Releaser DeadLetterReleaser
}

type deadLetterRecoveryRequest struct {
	SourceStreamID string `json:"sourceStreamId"`
}

// WithDeadLetterRecoveryRoute adds one operator-only service route around an
// existing service handler. Authentication and authorization remain owned by
// the generated operation guard declared in service metadata.
func WithDeadLetterRecoveryRoute(
	base http.Handler,
	config DeadLetterRecoveryRouteConfig,
) (http.Handler, error) {
	if base == nil || config.Releaser == nil {
		return nil, errors.New(
			"dead-letter recovery route requires base handler and releaser",
		)
	}
	config.Path = strings.TrimSpace(config.Path)
	if !strings.HasPrefix(config.Path, "/internal/") {
		return nil, errors.New(
			"dead-letter recovery route requires an internal absolute path",
		)
	}
	if strings.TrimSpace(string(config.Module)) == "" {
		return nil, errors.New("dead-letter recovery route requires error module")
	}
	mux := http.NewServeMux()
	mux.Handle(config.Path, deadLetterRecoveryHandler(config))
	mux.Handle("/", base)
	return mux, nil
}

func deadLetterRecoveryHandler(
	config DeadLetterRecoveryRouteConfig,
) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost {
			writer.Header().Set("Allow", http.MethodPost)
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewInvalidArgument(
					config.Module,
					"仅支持 POST 恢复请求",
					"dead-letter recovery route only accepts POST",
				).WithMetadata("invalid_argument", http.StatusMethodNotAllowed),
			)
			return
		}
		if strings.TrimSpace(request.Header.Get("Idempotency-Key")) == "" {
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewInvalidArgument(
					config.Module,
					"缺少幂等键",
					"dead-letter recovery requires Idempotency-Key",
				),
			)
			return
		}
		request.Body = http.MaxBytesReader(writer, request.Body, 4096)
		decoder := json.NewDecoder(request.Body)
		decoder.DisallowUnknownFields()
		var command deadLetterRecoveryRequest
		if err := decoder.Decode(&command); err != nil {
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewInvalidArgument(
					config.Module,
					"恢复请求格式无效",
					"invalid dead-letter recovery request",
				),
			)
			return
		}
		if err := requireJSONEOF(decoder); err != nil {
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewInvalidArgument(
					config.Module,
					"恢复请求只能包含一个对象",
					"dead-letter recovery request contains trailing data",
				),
			)
			return
		}
		command.SourceStreamID = strings.TrimSpace(command.SourceStreamID)
		if !isRedisStreamID(command.SourceStreamID) {
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewInvalidArgument(
					config.Module,
					"sourceStreamId 无效",
					"dead-letter recovery requires a canonical Redis stream ID",
				),
			)
			return
		}
		if err := config.Releaser.RecoverDeadLetter(
			request.Context(),
			command.SourceStreamID,
		); err != nil {
			writeDeadLetterRecoveryError(
				writer,
				request,
				rterr.NewAppError(
					rterr.NewCode(
						config.Module,
						rterr.KindSystem,
						"internal_error",
					),
					"暂时无法释放待恢复事件",
					"dead-letter source PEL release failed",
				),
			)
			return
		}
		writer.Header().Set("Content-Type", "application/json")
		writer.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(writer).Encode(map[string]any{
			"sourceStreamId":   command.SourceStreamID,
			"recoveryAccepted": true,
		})
	})
}

func requireJSONEOF(decoder *json.Decoder) error {
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

func isRedisStreamID(value string) bool {
	parts := strings.Split(value, "-")
	if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
		return false
	}
	for _, part := range parts {
		if _, err := strconv.ParseUint(part, 10, 64); err != nil {
			return false
		}
	}
	return true
}

func writeDeadLetterRecoveryError(
	writer http.ResponseWriter,
	request *http.Request,
	err *rterr.AppError,
) {
	rterr.WriteHTTPError(
		writer,
		err,
		rterr.HTTPWriteOptionsFromRequest(request),
	)
}
