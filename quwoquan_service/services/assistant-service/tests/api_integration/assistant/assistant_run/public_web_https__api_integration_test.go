// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-002
package assistant_run_integration

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"

	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	publicwebinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
)

type controlledDNS struct {
	addresses map[string][]netip.Addr
	lookups   []string
}

func (r *controlledDNS) LookupNetIP(
	_ context.Context,
	_ string,
	host string,
) ([]netip.Addr, error) {
	r.lookups = append(r.lookups, host)
	addresses, ok := r.addresses[host]
	if !ok {
		return nil, fmt.Errorf("controlled DNS has no host %q", host)
	}
	return append([]netip.Addr{}, addresses...), nil
}

type controlledHTTPSDialer struct {
	localAddress string
	dialed       []string
}

func (d *controlledHTTPSDialer) DialContext(
	ctx context.Context,
	network string,
	address string,
) (net.Conn, error) {
	d.dialed = append(d.dialed, address)
	return (&net.Dialer{}).DialContext(ctx, network, d.localAddress)
}

func TestPublicWebFabricUsesControlledHTTPSAndAuthoritativeMongoLedgers(t *testing.T) {
	resetPublicWebMongo(t)
	database := requirePublicWebMongo(t)

	var certificateHost string
	server := httptest.NewUnstartedServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			for _, name := range []string{"Authorization", "Cookie", "Proxy-Authorization", "Referer"} {
				if request.Header.Get(name) != "" {
					t.Errorf("credential header %s escaped the public web boundary", name)
				}
			}
			switch request.URL.Path {
			case "/start":
				http.Redirect(writer, request, "/final", http.StatusFound)
			case "/final":
				writer.Header().Set("Content-Type", "text/html; charset=utf-8")
				_, _ = writer.Write([]byte(
					`<html><head><title>Controlled Evidence</title></head>` +
						`<body><main>verified durable fact</main>` +
						`<a href="/next">Next source</a></body></html>`,
				))
			default:
				http.NotFound(writer, request)
			}
		},
	))
	server.StartTLS()
	defer server.Close()
	if len(server.Certificate().DNSNames) == 0 {
		t.Fatal("controlled HTTPS certificate has no DNS identity")
	}
	certificateHost = server.Certificate().DNSNames[0]

	rootCAs := x509.NewCertPool()
	rootCAs.AddCert(server.Certificate())
	dialer := &controlledHTTPSDialer{localAddress: server.Listener.Addr().String()}
	resolver := &controlledDNS{addresses: map[string][]netip.Addr{
		certificateHost: {netip.MustParseAddr("93.184.216.34")},
	}}
	policy := publicwebinfra.NewNetworkPolicy(resolver)
	transport := publicwebinfra.NewSecureTransportWithTLS(
		policy,
		dialer,
		&tls.Config{RootCAs: rootCAs},
	)
	fetcher := publicwebinfra.NewFetcherWithClient(
		policy,
		&http.Client{Transport: transport},
		publicwebinfra.DefaultFetchLimits(),
	)
	evidence := publicwebinfra.NewMongoEvidenceStore(database)
	budget := publicwebinfra.NewMongoRunBudgetGate(
		database,
		publicweb.RunBudgetLimits{MaxPages: 1, MaxBytes: 1 << 20},
	)
	if err := evidence.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	if err := budget.EnsureIndexes(t.Context()); err != nil {
		t.Fatal(err)
	}
	service := publicweb.NewService(
		publicweb.NewLedgerTargetResolver(evidence),
		fetcher,
		evidence,
		budget,
		publicweb.DefaultDocumentParser(),
	)
	fabric := publicwebtool.NewPublicWebFabric(
		unusedSearchDelegate,
		evidence,
		service,
		publicweb.NewFinder(evidence),
	)

	const runID = "run_controlled_https"
	openResult, err := fabric.Execute(t.Context(), publicwebtool.DurableRequest{
		ToolName: "web_open",
		RunID:    runID,
		SkillID:  "knowledge_general",
		Input: map[string]any{
			"runId":   "run_forged",
			"skillId": "skill_forged",
			"target": map[string]any{
				"kind":  "url",
				"value": "https://" + certificateHost + "/start",
			},
		},
	})
	if err != nil {
		t.Fatalf("execute controlled HTTPS web_open: %v", err)
	}
	documentOutput := openResult.Output["document"].(map[string]any)
	assessment := openResult.Output["evidenceAssessment"].(map[string]any)
	if assessment["evidenceSufficient"] != true ||
		assessment["replanRequired"] != false ||
		assessment["reason"] != "document_evidence_available" {
		t.Fatalf("open evidence assessment = %#v", assessment)
	}
	documentID := documentOutput["documentId"].(string)
	artifactRef := documentOutput["artifactRef"].(string)
	targetID := documentOutput["targetId"].(string)

	restarted := publicwebinfra.NewMongoEvidenceStore(database)
	document, err := restarted.ReadDocument(t.Context(), runID, documentID)
	if err != nil {
		t.Fatalf("read document after adapter restart: %v", err)
	}
	target, err := restarted.ReadTarget(t.Context(), runID, targetID)
	if err != nil || target.Requested.Value != "https://"+certificateHost+"/start" {
		t.Fatalf("read target ledger=%+v err=%v", target, err)
	}
	source, err := restarted.ReadSource(t.Context(), runID, document.Source.SourceID)
	if err != nil || source.TargetID != targetID || len(source.RedirectChain) != 1 {
		t.Fatalf("read source ledger=%+v err=%v", source, err)
	}
	artifact, err := restarted.ReadArtifact(t.Context(), runID, artifactRef)
	if err != nil || !strings.Contains(string(artifact.Body), "verified durable fact") {
		t.Fatalf("read artifact ledger=%+v err=%v", artifact, err)
	}
	count, err := database.Collection("assistant_run_web_evidence").
		CountDocuments(t.Context(), bson.M{"runId": runID})
	if err != nil || count != 4 {
		t.Fatalf("authoritative ledger record count=%d err=%v, want 4", count, err)
	}

	findResult, err := fabric.Execute(t.Context(), publicwebtool.DurableRequest{
		ToolName: "web_find",
		RunID:    runID,
		Input: map[string]any{
			"runId":      "run_forged",
			"documentId": documentID,
			"pattern":    "durable fact",
			"maxMatches": float64(5),
		},
	})
	if err != nil {
		t.Fatalf("execute durable web_find: %v", err)
	}
	findAssessment := findResult.Output["evidenceAssessment"].(map[string]any)
	if findAssessment["evidenceSufficient"] != true ||
		findAssessment["replanRequired"] != false {
		t.Fatalf("find evidence assessment = %#v", findAssessment)
	}
	if len(resolver.lookups) < 3 {
		t.Fatalf("initial URL, connection and redirect were not all DNS-revalidated: %v", resolver.lookups)
	}
	for _, address := range dialer.dialed {
		if address != "93.184.216.34:443" {
			t.Fatalf("secure transport dialed unvalidated address %q", address)
		}
	}

	_, err = fabric.Execute(t.Context(), publicwebtool.DurableRequest{
		ToolName: "web_open",
		RunID:    runID,
		Input: map[string]any{
			"target": map[string]any{
				"kind": "url", "value": "https://" + certificateHost + "/final",
			},
		},
	})
	if !errors.Is(err, publicweb.ErrBudgetExhausted) {
		t.Fatalf("durable page budget was not retained: %v", err)
	}
}

func TestControlledHTTPSRedirectCannotEscapeToPrivateIP(t *testing.T) {
	resetPublicWebMongo(t)
	database := requirePublicWebMongo(t)

	server := httptest.NewUnstartedServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			http.Redirect(
				writer,
				request,
				"https://169.254.169.254/latest/meta-data",
				http.StatusFound,
			)
		},
	))
	server.StartTLS()
	defer server.Close()
	if len(server.Certificate().DNSNames) == 0 {
		t.Fatal("controlled HTTPS certificate has no DNS identity")
	}
	host := server.Certificate().DNSNames[0]
	rootCAs := x509.NewCertPool()
	rootCAs.AddCert(server.Certificate())
	resolver := &controlledDNS{addresses: map[string][]netip.Addr{
		host: {netip.MustParseAddr("93.184.216.34")},
	}}
	policy := publicwebinfra.NewNetworkPolicy(resolver)
	dialer := &controlledHTTPSDialer{localAddress: server.Listener.Addr().String()}
	fetcher := publicwebinfra.NewFetcherWithClient(
		policy,
		&http.Client{Transport: publicwebinfra.NewSecureTransportWithTLS(
			policy,
			dialer,
			&tls.Config{RootCAs: rootCAs},
		)},
		publicwebinfra.DefaultFetchLimits(),
	)
	evidence := publicwebinfra.NewMongoEvidenceStore(database)
	budget := publicwebinfra.NewMongoRunBudgetGate(
		database,
		publicweb.RunBudgetLimits{MaxPages: 1, MaxBytes: 1 << 20},
	)
	service := publicweb.NewService(
		publicweb.NewLedgerTargetResolver(evidence),
		fetcher,
		evidence,
		budget,
		publicweb.DefaultDocumentParser(),
	)
	const runID = "run_private_redirect"
	_, err := service.Open(t.Context(), publicweb.OpenRequest{
		RunID: runID,
		Target: publicweb.Target{
			Kind: publicweb.TargetURL, Value: "https://" + host + "/escape",
		},
	})
	if !errors.Is(err, publicweb.ErrTargetRejected) {
		t.Fatalf("private redirect was not rejected: %v", err)
	}
	count, err := database.Collection("assistant_run_web_evidence").
		CountDocuments(t.Context(), bson.M{"runId": runID})
	if err != nil || count != 0 {
		t.Fatalf("rejected redirect wrote evidence count=%d err=%v", count, err)
	}
	reservation, err := budget.ReserveFetch(t.Context(), runID, 1024)
	if err != nil {
		t.Fatalf("rejected fetch leaked durable reservation: %v", err)
	}
	reservation.Release()
	if len(dialer.dialed) != 1 || dialer.dialed[0] != "93.184.216.34:443" {
		t.Fatalf("redirect boundary dialed unexpected address: %v", dialer.dialed)
	}
}

func unusedSearchDelegate(
	_ context.Context,
	_ toolpkg.Request,
) (toolpkg.Result, error) {
	return toolpkg.Result{}, errors.New("controlled HTTPS test does not invoke search")
}
