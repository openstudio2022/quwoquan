package main

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rthttp "quwoquan_service/runtime/http"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
)

func newHTTPServer(
	identity runtimeIdentity,
	cfg config,
	root http.Handler,
	authConfig rtauth.MiddlewareConfig,
) (*http.Server, func(), error) {
	shutdownTelemetry := rtotel.MustInit(rtotel.Config{
		ServiceName:   identity.ServiceName,
		SamplingRatio: 0.1,
	})
	exporter, err := robs.NewHTTPRuntimeLogFieldExporter(
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_URL")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_INGEST_TOKEN")),
		strings.TrimSpace(os.Getenv("RUNTIME_LOG_SPOOL_DIR")),
	)
	if err != nil {
		shutdownTelemetry()
		return nil, func() {}, fmt.Errorf("runtime log exporter invalid: %w", err)
	}
	standardWriter := robs.NewRuntimeLogExportWriter(os.Stdout, 512, exporter.Export)
	errorWriter := robs.NewRuntimeLogExportWriter(os.Stderr, 512, exporter.Export)
	processLogger, err := robs.NewProcessTraceLogger(standardWriter, errorWriter, "info", nil)
	if err != nil {
		standardWriter.Close()
		errorWriter.Close()
		exporter.Close()
		shutdownTelemetry()
		return nil, func() {}, fmt.Errorf("process logger invalid: %w", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(standardWriter, errorWriter, nil)
	if err != nil {
		standardWriter.Close()
		errorWriter.Close()
		exporter.Close()
		shutdownTelemetry()
		return nil, func() {}, fmt.Errorf("exception logger invalid: %w", err)
	}
	instanceID, _ := os.Hostname()
	observed := rthttp.NewHTTPServerMiddleware(
		root,
		rthttp.HTTPServerMiddlewareConfig{
			Service: identity.ServiceName, ServiceName: identity.ServiceName,
			ServiceInstanceID: instanceID, Origin: "cloud", Direction: "inbound",
			SourceID: identity.ServiceName + ".http", Src: "gateway",
		},
		robs.NewIOAccessLogger(standardWriter),
		processLogger,
		exceptionLogger,
	)
	handler := rtauth.Middleware(authConfig)(
		rthttp.WithCORS(observed, rthttp.CORSOptionsFromEnv()),
	)
	cleanup := func() {
		standardWriter.Close()
		errorWriter.Close()
		exporter.Close()
		shutdownTelemetry()
	}
	return &http.Server{
		Addr: cfg.Service.HTTP.Addr, Handler: handler,
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}, cleanup, nil
}

func serveGracefully(server *http.Server) error {
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		return fmt.Errorf("travel-service HTTP server: %w", err)
	}
	return nil
}
