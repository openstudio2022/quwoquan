package httpcodec

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"strconv"
	"strings"
)

const defaultJSONBodyLimit = int64(1 << 20)

// DecodeStrictJSON accepts exactly one JSON value and rejects unknown fields.
// Domain adapters remain responsible for mapping this transport error to their
// canonical runtime error code.
func DecodeStrictJSON(request *http.Request, target any) error {
	if request == nil || request.Body == nil || target == nil {
		return fmt.Errorf("request body and decode target are required")
	}
	decoder := json.NewDecoder(io.LimitReader(request.Body, defaultJSONBodyLimit))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return fmt.Errorf("request body must contain exactly one JSON value")
		}
		return err
	}
	return nil
}

func ParsePositiveEntityTag(raw string) (int64, error) {
	normalized := strings.TrimSpace(raw)
	normalized = strings.TrimPrefix(normalized, "W/")
	normalized = strings.Trim(normalized, "\"")
	value, err := strconv.ParseInt(normalized, 10, 64)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("If-Match must contain a positive aggregate version")
	}
	return value, nil
}

func WriteJSON(writer http.ResponseWriter, status int, value any, component string) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		slog.Default().Warn(
			"HTTP JSON response encode failed",
			"component", strings.TrimSpace(component),
			"error", err,
		)
	}
}
