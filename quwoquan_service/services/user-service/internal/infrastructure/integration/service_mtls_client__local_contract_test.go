package integration

import (
	"crypto/rand"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestIntegrationServiceMTLSClientFailsClosedWithoutSecretMaterial(t *testing.T) {
	for _, name := range []string{
		integrationServiceMTLSCAFileEnv,
		integrationServiceMTLSCertFileEnv,
		integrationServiceMTLSKeyFileEnv,
	} {
		t.Setenv(name, "")
	}
	if _, err := NewIntegrationServiceMTLSClient(time.Second); err == nil {
		t.Fatal("missing mTLS secret material must fail closed")
	}
}

func TestIntegrationServiceMTLSClientVerifiesServerAndPresentsCertificate(t *testing.T) {
	dir := t.TempDir()
	caCert, caKey, caPEM := issueTestCA(t)
	serverCertPEM, serverKeyPEM := issueTestCertificate(t, caCert, caKey, true)
	clientCertPEM, clientKeyPEM := issueTestCertificate(t, caCert, caKey, false)

	caFile := writeTestPEM(t, dir, "ca.pem", caPEM)
	clientCertFile := writeTestPEM(t, dir, "client.pem", clientCertPEM)
	clientKeyFile := writeTestPEM(t, dir, "client-key.pem", clientKeyPEM)
	t.Setenv(integrationServiceMTLSCAFileEnv, caFile)
	t.Setenv(integrationServiceMTLSCertFileEnv, clientCertFile)
	t.Setenv(integrationServiceMTLSKeyFileEnv, clientKeyFile)
	t.Setenv(integrationServiceMTLSServerNameEnv, "localhost")

	serverPair, err := tls.X509KeyPair(serverCertPEM, serverKeyPEM)
	if err != nil {
		t.Fatalf("parse server key pair: %v", err)
	}
	clientCAs := x509.NewCertPool()
	clientCAs.AppendCertsFromPEM(caPEM)
	server := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.TLS == nil || len(r.TLS.PeerCertificates) == 0 {
			t.Error("request did not present a verified client certificate")
			http.Error(w, "client certificate required", http.StatusUnauthorized)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))
	server.TLS = &tls.Config{
		MinVersion:   tls.VersionTLS13,
		Certificates: []tls.Certificate{serverPair},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    clientCAs,
	}
	server.StartTLS()
	defer server.Close()

	client, err := NewIntegrationServiceMTLSClient(2 * time.Second)
	if err != nil {
		t.Fatalf("build mTLS client: %v", err)
	}
	response, err := client.Get(server.URL)
	if err != nil {
		t.Fatalf("mTLS request: %v", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", response.StatusCode, http.StatusNoContent)
	}
}

func issueTestCA(t *testing.T) (*x509.Certificate, *rsa.PrivateKey, []byte) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate CA key: %v", err)
	}
	template := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "quwoquan-test-ca"},
		NotBefore:             time.Now().Add(-time.Minute),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if err != nil {
		t.Fatalf("create CA certificate: %v", err)
	}
	certificate, err := x509.ParseCertificate(der)
	if err != nil {
		t.Fatalf("parse CA certificate: %v", err)
	}
	return certificate, key, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
}

func issueTestCertificate(
	t *testing.T,
	ca *x509.Certificate,
	caKey *rsa.PrivateKey,
	server bool,
) ([]byte, []byte) {
	t.Helper()
	key, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatalf("generate leaf key: %v", err)
	}
	serial := int64(2)
	usage := []x509.ExtKeyUsage{x509.ExtKeyUsageClientAuth}
	commonName := "user-service"
	dnsNames := []string(nil)
	if server {
		serial = 3
		usage = []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}
		commonName = "integration-service"
		dnsNames = []string{"localhost"}
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(serial),
		Subject:      pkix.Name{CommonName: commonName},
		DNSNames:     dnsNames,
		NotBefore:    time.Now().Add(-time.Minute),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment,
		ExtKeyUsage:  usage,
	}
	der, err := x509.CreateCertificate(rand.Reader, template, ca, &key.PublicKey, caKey)
	if err != nil {
		t.Fatalf("create leaf certificate: %v", err)
	}
	keyDER, err := x509.MarshalPKCS8PrivateKey(key)
	if err != nil {
		t.Fatalf("marshal leaf key: %v", err)
	}
	return pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: keyDER})
}

func writeTestPEM(t *testing.T, dir, name string, value []byte) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, value, 0o600); err != nil {
		t.Fatalf("write %s: %v", name, err)
	}
	return path
}
