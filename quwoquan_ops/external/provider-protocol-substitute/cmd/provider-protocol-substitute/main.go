package main

import (
	"crypto/tls"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"quwoquan_provider_protocol_substitute/internal/server"
)

func main() {
	handler, err := server.New(server.Config{
		Environment:         required("APP_ENV"),
		ConfigurationDigest: required("PROVIDER_SUBSTITUTE_CONFIGURATION_DIGEST"),
		OperatorToken:       required("PROVIDER_SUBSTITUTE_OPERATOR_TOKEN"),
		DefaultScenario:     strings.TrimSpace(os.Getenv("PROVIDER_SUBSTITUTE_SCENARIO")),
	})
	if err != nil {
		log.Fatal(err)
	}
	httpServer := &http.Server{
		Addr:              envOr("PROVIDER_SUBSTITUTE_ADDR", ":18089"),
		Handler:           handler.Handler(),
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       10 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    16 << 10,
		TLSConfig:         &tls.Config{MinVersion: tls.VersionTLS13},
	}
	log.Printf(
		"provider protocol substitute ready environment=%s adapter=%s",
		required("APP_ENV"),
		server.AdapterID,
	)
	log.Fatal(httpServer.ListenAndServeTLS(
		required("PROVIDER_SUBSTITUTE_TLS_CERT_FILE"),
		required("PROVIDER_SUBSTITUTE_TLS_KEY_FILE"),
	))
}

func required(key string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		log.Fatalf("%s is required", key)
	}
	return value
}

func envOr(key, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
