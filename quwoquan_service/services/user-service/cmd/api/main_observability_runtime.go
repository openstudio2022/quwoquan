package main

import (
	"net/http"
	"os"
	"strings"

	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
)

// buildObservedUserHandler owns the process log sinks and the canonical HTTP
// observability/CORS wrapper. The returned cleanup preserves the original
// shutdown order: drain writers before stopping their remote exporter.
func buildObservedUserHandler(next http.Handler) (http.Handler, func(), error) {
	runtimeLogExporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		return nil, nil, err
	}
	standardLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stdout,
		512,
		runtimeLogExporter.Export,
	)
	errorLogWriter := robs.NewRuntimeLogExportWriter(
		os.Stderr,
		512,
		runtimeLogExporter.Export,
	)
	cleanup := func() {
		errorLogWriter.Close()
		standardLogWriter.Close()
		runtimeLogExporter.Close()
	}

	ioLogger := robs.NewIOAccessLogger(standardLogWriter)
	processLogger, err := robs.NewProcessTraceLogger(
		standardLogWriter,
		errorLogWriter,
		"info",
		nil,
	)
	if err != nil {
		cleanup()
		return nil, nil, err
	}
	exceptionLogger, err := robs.NewExceptionLogger(
		standardLogWriter,
		errorLogWriter,
		nil,
	)
	if err != nil {
		cleanup()
		return nil, nil, err
	}
	instanceID, _ := os.Hostname()
	observedHandler := rthttp.NewHTTPServerMiddleware(
		next,
		rthttp.HTTPServerMiddlewareConfig{
			Service:           "user-service",
			ServiceName:       "user-service",
			ServiceInstanceID: instanceID,
		},
		ioLogger,
		processLogger,
		exceptionLogger,
	)
	return rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv()), cleanup, nil
}
