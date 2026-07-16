package integration

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

const (
	integrationServiceMTLSCAFileEnv     = "INTEGRATION_SERVICE_MTLS_CA_FILE"
	integrationServiceMTLSCertFileEnv   = "INTEGRATION_SERVICE_MTLS_CLIENT_CERT_FILE"
	integrationServiceMTLSKeyFileEnv    = "INTEGRATION_SERVICE_MTLS_CLIENT_KEY_FILE"
	integrationServiceMTLSServerNameEnv = "INTEGRATION_SERVICE_MTLS_SERVER_NAME"
)

// NewIntegrationServiceMTLSClient creates the only production transport used
// by user-service for internal ExternalInteraction operations. Secret Manager
// mounts the certificate files; missing or invalid material is fail-closed.
func NewIntegrationServiceMTLSClient(timeout time.Duration) (*http.Client, error) {
	caFile, err := requiredMTLSEnv(integrationServiceMTLSCAFileEnv)
	if err != nil {
		return nil, err
	}
	certFile, err := requiredMTLSEnv(integrationServiceMTLSCertFileEnv)
	if err != nil {
		return nil, err
	}
	keyFile, err := requiredMTLSEnv(integrationServiceMTLSKeyFileEnv)
	if err != nil {
		return nil, err
	}

	caPEM, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("read integration service mTLS CA: %w", err)
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("integration service mTLS CA contains no certificate")
	}
	certificate, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("load integration service mTLS client certificate: %w", err)
	}
	if timeout <= 0 {
		timeout = 3 * time.Second
	}
	transport := &http.Transport{
		Proxy: http.ProxyFromEnvironment,
		TLSClientConfig: &tls.Config{
			MinVersion:   tls.VersionTLS13,
			RootCAs:      roots,
			Certificates: []tls.Certificate{certificate},
			ServerName:   strings.TrimSpace(os.Getenv(integrationServiceMTLSServerNameEnv)),
		},
		ForceAttemptHTTP2: true,
	}
	return &http.Client{Transport: transport, Timeout: timeout}, nil
}

func requiredMTLSEnv(name string) (string, error) {
	value := strings.TrimSpace(os.Getenv(name))
	if value == "" {
		return "", fmt.Errorf("%s is required for integration service mTLS", name)
	}
	return value, nil
}
