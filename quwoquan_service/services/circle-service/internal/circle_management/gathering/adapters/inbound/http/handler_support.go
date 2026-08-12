package http

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	stdhttp "net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
)

func splitAction(raw string) (string, string) {
	parts := strings.Split(raw, ":")
	if len(parts) == 1 {
		return strings.TrimSpace(parts[0]), ""
	}
	if len(parts) != 2 {
		return "", ""
	}
	return strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
}

func decodeStrictJSON(reader io.Reader, target any) error {
	decoder := json.NewDecoder(io.LimitReader(reader, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return fmt.Errorf("request body must contain exactly one JSON object")
		}
		return err
	}
	return nil
}

func readStrictJSON(request *stdhttp.Request, target any) error {
	return decodeStrictJSON(request.Body, target)
}

func writeJSON(writer stdhttp.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		slog.Default().Warn("Gathering response encode failed", "error", err)
	}
}

func writeError(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	err error,
) {
	rterr.WriteHTTPError(
		writer,
		err,
		rterr.HTTPWriteOptionsFromRequest(request),
	)
}
