package runtimeobservability

import (
	"encoding/json"
	"io"
)

type ProcessTraceLogger struct {
	router      *SinkRouter
	level       string
	kvFilter    *KVMetadataFilter
}

func NewProcessTraceLogger(standardSink io.Writer, errorSink io.Writer, level string, kvFilter *KVMetadataFilter) (*ProcessTraceLogger, error) {
	router, err := NewSinkRouter(standardSink, errorSink)
	if err != nil {
		return nil, err
	}
	if level == "" {
		level = TraceLogLevelInfo
	}
	return &ProcessTraceLogger{
		router:      router,
		level:       level,
		kvFilter:    kvFilter,
	}, nil
}

func (l *ProcessTraceLogger) Write(entry ProcessTraceLog, model string, operation string, input map[string]any, output map[string]any) error {
	if l.level == TraceLogLevelOff {
		return nil
	}
	if l.level == TraceLogLevelInfo && entry.Level == TraceLogLevelDebug {
		return nil
	}

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
	entry.IO = ProcessTraceIO{InputKV: inKV, OutputKV: outKV}

	if err := entry.Validate(); err != nil {
		return err
	}
	payload, err := json.Marshal(entry)
	if err != nil {
		return err
	}
	return l.router.WriteStandard(append(payload, '\n'))
}

