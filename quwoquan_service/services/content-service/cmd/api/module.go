package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"sync"
	"sync/atomic"

	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/runtime/servicehost"
)

type workerRegistry struct {
	starts []func(context.Context)
}

func (registry *workerRegistry) Add(start func(context.Context)) {
	if start != nil {
		registry.starts = append(registry.starts, start)
	}
}

// Module keeps content-service's private composition and worker ownership
// together. servicehost owns process signals and global admission sequencing.
type Module struct {
	configDigest string
	server       *http.Server
	health       *rthealth.Checker
	listener     net.Listener
	admission    atomic.Bool
	serveError   chan error

	workerStarts []func(context.Context)
	workerCancel context.CancelFunc
	workerGroup  sync.WaitGroup
	runContext   context.Context
	cleanup      func()
}

var _ servicehost.Module = (*Module)(nil)

func (module *Module) Name() string { return "content-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil {
		return errors.New("content-service module is incomplete")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("content-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("content-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("content-service listener is not bound")
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	for _, start := range module.workerStarts {
		module.workerGroup.Add(1)
		module.startWorker(start)
	}
	module.workerGroup.Add(1)
	go func() {
		defer module.workerGroup.Done()
		if err := module.server.Serve(module.listener); err != nil && !errors.Is(err, http.ErrServerClosed) {
			select {
			case module.serveError <- err:
			case <-module.runContext.Done():
			}
		}
	}()
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	if result := module.health.Check(ctx); result.Status != "ok" {
		return fmt.Errorf("content-service readiness failed: %v", result.FailedChecks)
	}
	select {
	case err := <-module.serveError:
		return fmt.Errorf("content-service listener failed: %w", err)
	default:
		return nil
	}
}

func (module *Module) OpenAdmission(context.Context) error {
	module.admission.Store(true)
	return nil
}

func (module *Module) Shutdown(ctx context.Context) error {
	module.admission.Store(false)
	if module.workerCancel != nil {
		module.workerCancel()
		module.workerCancel = nil
	}

	var result error
	if module.server != nil {
		result = errors.Join(result, module.server.Shutdown(ctx))
	}
	result = errors.Join(result, module.waitForWorkers(ctx))
	if module.cleanup != nil {
		module.cleanup()
		module.cleanup = nil
	}
	return result
}

func (module *Module) startWorker(start func(context.Context)) {
	go func() {
		defer module.workerGroup.Done()
		start(module.runContext)
	}()
}

func (module *Module) waitForWorkers(ctx context.Context) error {
	done := make(chan struct{})
	go func() {
		module.workerGroup.Wait()
		close(done)
	}()
	select {
	case <-done:
		return nil
	case <-ctx.Done():
		return ctx.Err()
	}
}

func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/livez", "/startupz", "/metrics":
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admission.Load() {
			http.Error(writer, `{"status":"unavailable"}`, http.StatusServiceUnavailable)
			return
		}
		next.ServeHTTP(writer, request)
	})
}
