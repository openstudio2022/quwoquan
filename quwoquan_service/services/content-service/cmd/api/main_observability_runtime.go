package main

import (
	"log"
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

// mustBuildContentRuntimeLogging 装配进程日志出口，不选择任何业务对象实现。
func mustBuildContentRuntimeLogging() *contentRuntimeLogging {
	exporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		log.Fatalf("content-service runtime log exporter init failed: %v", err)
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
		log.Fatalf("content-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardWriter, errorWriter, nil)
	if err != nil {
		log.Fatalf("content-service exception logger init failed: %v", err)
	}
	return &contentRuntimeLogging{
		exporter:        exporter,
		standardWriter:  standardWriter,
		errorWriter:     errorWriter,
		ioLogger:        robs.NewIOAccessLogger(standardWriter),
		processLogger:   processLogger,
		exceptionLogger: exceptionLogger,
	}
}

func (runtime *contentRuntimeLogging) Close() {
	runtime.errorWriter.Close()
	runtime.standardWriter.Close()
	runtime.exporter.Close()
}
