package bootstrap

import (
	"fmt"
	"os"
	"strings"

	robs "quwoquan_service/runtime/observability"
)

type contentRuntimeLogging struct {
	exporter        *robs.HTTPRuntimeLogExporter
	standardWriter  *robs.RuntimeLogExportWriter
	errorWriter     *robs.RuntimeLogExportWriter
	ioLogger        *robs.IOAccessLogger
	processLogger   *robs.ProcessTraceLogger
	exceptionLogger *robs.ExceptionLogger
}

// buildContentRuntimeLogging 装配进程日志出口，不选择任何业务对象实现。
func buildContentRuntimeLogging() (*contentRuntimeLogging, error) {
	exporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, fmt.Errorf("content-service runtime log exporter init failed: %w", err)
	}
	standardWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, exporter.Export)
	errorWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, exporter.Export)
	processLogger, err := robs.NewProcessTraceLogger(
		standardWriter,
		errorWriter,
		"info",
		nil,
	)
	if err != nil {
		errorWriter.Close()
		standardWriter.Close()
		exporter.Close()
		return nil, fmt.Errorf("content-service process logger init failed: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardWriter, errorWriter, nil)
	if err != nil {
		errorWriter.Close()
		standardWriter.Close()
		exporter.Close()
		return nil, fmt.Errorf("content-service exception logger init failed: %w", err)
	}
	return &contentRuntimeLogging{
		exporter:        exporter,
		standardWriter:  standardWriter,
		errorWriter:     errorWriter,
		ioLogger:        robs.NewIOAccessLogger(standardWriter),
		processLogger:   processLogger,
		exceptionLogger: exceptionLogger,
	}, nil
}

func (runtime *contentRuntimeLogging) Close() {
	runtime.errorWriter.Close()
	runtime.standardWriter.Close()
	runtime.exporter.Close()
}
