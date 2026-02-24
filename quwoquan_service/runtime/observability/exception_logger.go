package runtimeobservability

import (
	"encoding/json"
	"io"
)

type ExceptionLogger struct {
	router   *SinkRouter
	kvFilter *KVMetadataFilter
}

func NewExceptionLogger(standardSink io.Writer, errorSink io.Writer, kvFilter *KVMetadataFilter) (*ExceptionLogger, error) {
	router, err := NewSinkRouter(standardSink, errorSink)
	if err != nil {
		return nil, err
	}
	return &ExceptionLogger{
		router:   router,
		kvFilter: kvFilter,
	}, nil
}

func (l *ExceptionLogger) Write(entry ExceptionLog, model string, operation string, input map[string]any, output map[string]any) error {
	inKV, outKV := map[string]any{}, map[string]any{}
	if l.kvFilter != nil {
		filteredInput, err := l.kvFilter.FilterInput(model, operation, input)
		if err != nil {
			return err
		}
		filteredOutput, err := l.kvFilter.FilterOutput(model, operation, output)
		if err != nil {
			return err
		}
		inKV = filteredInput
		outKV = filteredOutput
	}
	entry.IO = ExceptionIO{InputKV: inKV, OutputKV: outKV}

	if err := entry.Validate(); err != nil {
		return err
	}
	payload, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	return l.router.WriteError(append(payload, '\n'))
}

