package servicekit

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rthealth "quwoquan_service/runtime/health"
)

func validModuleSpec(t *testing.T) ModuleSpec {
	t.Helper()
	workers := &WorkerRegistry{}
	workers.Add(func(ctx context.Context) { <-ctx.Done() })
	return ModuleSpec{
		Identity:     Identity{ServiceName: "circle-service", AppEnv: "alpha"},
		ListenAddr:   "127.0.0.1:0",
		ConfigDigest: "sha256:abc",
		Handler: http.HandlerFunc(func(writer http.ResponseWriter, _ *http.Request) {
			writer.WriteHeader(http.StatusOK)
		}),
		Timeouts: HTTPServerTimeouts{
			ReadHeader: 5 * time.Second,
			Write:      10 * time.Second,
			Idle:       30 * time.Second,
		},
		Health:   rthealth.NewChecker(),
		Workers:  workers,
		Cleanups: &CleanupStack{},
	}
}

func TestNewModuleFailsClosedOnMissingSpecFields(t *testing.T) {
	mutations := map[string]func(*ModuleSpec){
		"identity":      func(spec *ModuleSpec) { spec.Identity = Identity{} },
		"listen addr":   func(spec *ModuleSpec) { spec.ListenAddr = "" },
		"config digest": func(spec *ModuleSpec) { spec.ConfigDigest = "" },
		"handler":       func(spec *ModuleSpec) { spec.Handler = nil },
		"health":        func(spec *ModuleSpec) { spec.Health = nil },
		"workers":       func(spec *ModuleSpec) { spec.Workers = nil },
		"cleanups":      func(spec *ModuleSpec) { spec.Cleanups = nil },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			spec := validModuleSpec(t)
			mutate(&spec)
			if _, err := NewModule(spec); err == nil {
				t.Fatalf("expected fail-closed error for missing %s", name)
			}
		})
	}
}

// 零个 worker 是纯 HTTP 服务（如脚手架初始服务）的合法形态：注册器必须声明，
// 内容允许为空。
func TestNewModuleAcceptsEmptyWorkerRegistry(t *testing.T) {
	spec := validModuleSpec(t)
	spec.Workers = &WorkerRegistry{}
	module, err := NewModule(spec)
	if err != nil {
		t.Fatalf("empty worker registry must be accepted: %v", err)
	}
	if err := module.ValidateConfig(context.Background()); err != nil {
		t.Fatalf("zero-worker module must pass ValidateConfig: %v", err)
	}
}

func TestModuleLifecycleContract(t *testing.T) {
	module, err := NewModule(validModuleSpec(t))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if module.Name() != "circle-service" {
		t.Fatalf("unexpected module name %s", module.Name())
	}
	if module.ConfigDigest() != "sha256:abc" {
		t.Fatalf("unexpected config digest %s", module.ConfigDigest())
	}
	if err := module.ValidateConfig(context.Background()); err != nil {
		t.Fatalf("valid module must pass ValidateConfig: %v", err)
	}
	if err := module.PrepareMigration(context.Background()); err != nil {
		t.Fatalf("optional migration hook must default to no-op: %v", err)
	}
}

func TestAdmissionGateRejectsTrafficUntilOpened(t *testing.T) {
	module, err := NewModule(validModuleSpec(t))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	handler := module.server.Handler

	request := httptest.NewRequest(http.MethodGet, "/circles/c1", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusServiceUnavailable {
		t.Fatalf("expected 503 before OpenAdmission, got %d", recorder.Code)
	}

	for _, alwaysOn := range []string{"/healthz", "/readyz", "/metrics"} {
		probe := httptest.NewRecorder()
		handler.ServeHTTP(probe, httptest.NewRequest(http.MethodGet, alwaysOn, nil))
		if probe.Code != http.StatusOK {
			t.Fatalf("expected %s to bypass admission, got %d", alwaysOn, probe.Code)
		}
	}

	if err := module.OpenAdmission(context.Background()); err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	opened := httptest.NewRecorder()
	handler.ServeHTTP(opened, httptest.NewRequest(http.MethodGet, "/circles/c1", nil))
	if opened.Code != http.StatusOK {
		t.Fatalf("expected 200 after OpenAdmission, got %d", opened.Code)
	}
}

func TestModuleStartServesAndShutdownReleasesWorkers(t *testing.T) {
	module, err := NewModule(validModuleSpec(t))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	ctx := context.Background()
	if err := module.Bind(ctx); err != nil {
		t.Fatalf("bind failed: %v", err)
	}
	if err := module.Start(ctx); err != nil {
		t.Fatalf("start failed: %v", err)
	}
	if err := module.Ready(ctx); err != nil {
		t.Fatalf("ready failed: %v", err)
	}
	if err := module.OpenAdmission(ctx); err != nil {
		t.Fatalf("open admission failed: %v", err)
	}

	response, err := http.Get("http://" + module.listener.Addr().String() + "/circles/c1")
	if err != nil {
		t.Fatalf("live request failed: %v", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		t.Fatalf("expected 200 from live server, got %d", response.StatusCode)
	}

	shutdownCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := module.Shutdown(shutdownCtx); err != nil {
		t.Fatalf("shutdown failed: %v", err)
	}
}
