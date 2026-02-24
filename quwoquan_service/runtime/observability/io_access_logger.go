package runtimeobservability

import (
	"encoding/json"
	"fmt"
	"io"
	"regexp"
)

var errorCodePattern = regexp.MustCompile(`^[A-Z_]+\.(USER|SYSTEM|NETWORK|MIDDLEWARE)\.[a-z0-9_]+$`)

type IOAccessLogger struct {
	writer io.Writer
}

func NewIOAccessLogger(writer io.Writer) *IOAccessLogger {
	return &IOAccessLogger{writer: writer}
}

func (l *IOAccessLogger) Write(entry IOAccessLog) error {
	if err := entry.Validate(); err != nil {
		return err
	}
	if entry.ErrorCode != "" && !errorCodePattern.MatchString(entry.ErrorCode) {
		return fmt.Errorf("invalid errorCode format: %s", entry.ErrorCode)
	}

	payload, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	_, err = l.writer.Write(append(payload, '\n'))
	return err
}

