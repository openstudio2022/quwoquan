package rtotel

import (
	"strings"
	"testing"
)

// trace 是否加密传输只由 endpoint 的 scheme 声明。缺 scheme 判否而不是默默明文：
// 改之前的判据是 HasPrefix(endpoint, "https")，而注入面给的是 host:port，那个前缀
// 永远不成立，明文是唯一可达分支且不产生任何信号。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-005.t1
func TestParseOTLPTargetTakesTransportFromDeclaredScheme(t *testing.T) {
	for _, tc := range []struct {
		name         string
		endpoint     string
		wantHost     string
		wantPath     string
		wantInsecure bool
	}{
		{
			name:         "http declares plaintext",
			endpoint:     "http://otel-collector:4318",
			wantHost:     "otel-collector:4318",
			wantInsecure: true,
		},
		{
			name:     "https declares tls",
			endpoint: "https://collector.example.com:4318",
			wantHost: "collector.example.com:4318",
		},
		{
			name:     "path is carried through",
			endpoint: "https://collector.example.com/otlp/v1/traces",
			wantHost: "collector.example.com",
			wantPath: "/otlp/v1/traces",
		},
		{
			name:     "bare root path is not a url path override",
			endpoint: "https://collector.example.com/",
			wantHost: "collector.example.com",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			target, err := parseOTLPTarget(tc.endpoint)
			if err != nil {
				t.Fatalf("parseOTLPTarget(%q) rejected a valid endpoint: %v", tc.endpoint, err)
			}
			if target.host != tc.wantHost {
				t.Errorf("host = %q, want %q", target.host, tc.wantHost)
			}
			if target.urlPath != tc.wantPath {
				t.Errorf("urlPath = %q, want %q", target.urlPath, tc.wantPath)
			}
			if target.insecure != tc.wantInsecure {
				t.Errorf("insecure = %v, want %v", target.insecure, tc.wantInsecure)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-005.t2
func TestParseOTLPTargetRejectsUndeclaredTransport(t *testing.T) {
	for _, tc := range []struct {
		name        string
		endpoint    string
		wantMessage string
	}{
		{
			name:        "host port without scheme",
			endpoint:    "otel-collector:4318",
			wantMessage: "must declare its transport",
		},
		{
			name:        "scheme relative",
			endpoint:    "//otel-collector:4318",
			wantMessage: "must declare its transport",
		},
		{
			name:        "unsupported scheme",
			endpoint:    "grpc://otel-collector:4317",
			wantMessage: "must declare its transport",
		},
		{
			name:        "scheme without host",
			endpoint:    "http://",
			wantMessage: "declares no host",
		},
	} {
		t.Run(tc.name, func(t *testing.T) {
			_, err := parseOTLPTarget(tc.endpoint)
			if err == nil {
				t.Fatalf("parseOTLPTarget(%q) accepted an endpoint with no declared transport", tc.endpoint)
			}
			if !strings.Contains(err.Error(), tc.wantMessage) {
				t.Errorf("error = %q, want it to mention %q", err.Error(), tc.wantMessage)
			}
		})
	}
}

// 判否必须止于装配：exporter 声明非法时退化成 no-op provider 会让服务带着「无
// trace」运行，而无 trace 与安静服务在外部看起来一样。
//
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/explicit-semantics-no-implicit-inference/spec.md#gwt-005.t3
func TestMustInitPanicsOnRejectedExporterDeclaration(t *testing.T) {
	t.Setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4318")
	defer func() {
		recovered := recover()
		if recovered == nil {
			t.Fatal("MustInit accepted an endpoint with no declared transport")
		}
		if message, ok := recovered.(string); !ok ||
			!strings.Contains(message, "must declare its transport") {
			t.Fatalf("panic value = %v, want it to name the missing declaration", recovered)
		}
	}()
	MustInit(Config{ServiceName: "otel-contract-test"})
}
