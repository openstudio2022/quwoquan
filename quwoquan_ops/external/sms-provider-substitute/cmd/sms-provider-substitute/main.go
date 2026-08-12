package main

import (
	"crypto/tls"
	"encoding/base64"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"quwoquan_sms_provider_substitute/internal/server"
)

func main() {
	if len(os.Args) == 2 && os.Args[1] == "healthcheck" {
		if err := runTLSHealthcheck(
			"https://127.0.0.1:9443/healthz",
			"/run/secrets/sms-provider-substitute/ca.crt",
		); err != nil {
			log.Printf("SMS substitute healthcheck failed: %v", err)
			os.Exit(1)
		}
		return
	}
	captureKey, err := base64.StdEncoding.DecodeString(required("SMS_SUBSTITUTE_CAPTURE_KEY_B64"))
	if err != nil {
		log.Fatal("SMS substitute capture key is invalid")
	}
	handler, err := server.New(server.Config{
		Environment: required("APP_ENV"), ConfigurationDigest: required("SMS_SUBSTITUTE_CONFIGURATION_DIGEST"),
		ProviderToken: required("SMS_SUBSTITUTE_PROVIDER_TOKEN"),
		OperatorToken: required("SMS_SUBSTITUTE_OPERATOR_TOKEN"), CaptureKey: captureKey,
		DefaultScene: strings.TrimSpace(os.Getenv("SMS_SUBSTITUTE_SCENARIO")),
	})
	if err != nil {
		log.Fatal(err)
	}
	httpServer := &http.Server{
		Addr:              envOr("SMS_SUBSTITUTE_ADDR", ":9443"),
		Handler:           handler.Handler(),
		ReadHeaderTimeout: 3 * time.Second,
		ReadTimeout:       5 * time.Second,
		WriteTimeout:      20 * time.Second,
		IdleTimeout:       30 * time.Second,
		MaxHeaderBytes:    16 << 10,
		TLSConfig:         &tls.Config{MinVersion: tls.VersionTLS13},
	}
	log.Printf("sms debug protocol substitute ready environment=%s adapter=%s", required("APP_ENV"), server.AdapterID)
	log.Fatal(httpServer.ListenAndServeTLS(required("SMS_SUBSTITUTE_TLS_CERT_FILE"), required("SMS_SUBSTITUTE_TLS_KEY_FILE")))
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
