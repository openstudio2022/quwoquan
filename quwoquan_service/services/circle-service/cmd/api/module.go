package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"sync"
	"sync/atomic"
	"time"

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

type cleanupStack struct {
	entries []func(context.Context) error
}

func (stack *cleanupStack) Add(cleanup func(context.Context) error) {
	if cleanup != nil {
		stack.entries = append(stack.entries, cleanup)
	}
}

func (stack *cleanupStack) Close(ctx context.Context) error {
	var result error
	for index := len(stack.entries) - 1; index >= 0; index-- {
		result = errors.Join(result, stack.entries[index](ctx))
	}
	stack.entries = nil
	return result
}

// Module keeps circle-service's private composition and worker ownership
// together. servicehost owns listener admission and process lifecycle.
type Module struct {
	appEnv       string
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
	cleanup      func(context.Context) error
}

var _ servicehost.Module = (*Module)(nil)

func (module *Module) Name() string { return "circle-service" }

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil {
		return errors.New("circle-service module is incomplete")
	}
	if len(module.workerStarts) == 0 {
		return errors.New("circle-service background workers are missing")
	}
	return nil
}

func (module *Module) PrepareMigration(context.Context) error {
	return nil
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return errors.New("circle-service HTTP server is unavailable")
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("circle-service listener bind: %w", err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return errors.New("circle-service listener is not bound")
	}
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("circle-service start context: %w", err)
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
	log.Printf("circle-service listening on %s (env=%s)", module.server.Addr, module.appEnv)
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	readinessCtx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	var failedChecks []string
	for {
		select {
		case err := <-module.serveError:
			return fmt.Errorf("circle-service listener failed: %w", err)
		default:
		}
		result := module.health.Check(readinessCtx)
		failedChecks = result.FailedChecks
		if result.Status == "ok" {
			select {
			case err := <-module.serveError:
				return fmt.Errorf("circle-service listener failed: %w", err)
			default:
				return nil
			}
		}
		select {
		case err := <-module.serveError:
			return fmt.Errorf("circle-service listener failed: %w", err)
		case <-readinessCtx.Done():
			return fmt.Errorf(
				"circle-service readiness failed: %v: %w",
				failedChecks,
				readinessCtx.Err(),
			)
		case <-ticker.C:
		}
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
	if module.listener != nil {
		_ = module.listener.Close()
		module.listener = nil
	}
	result = errors.Join(result, module.waitForWorkers(ctx))
	if module.cleanup != nil {
		result = errors.Join(result, module.cleanup(ctx))
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
		case "/healthz", "/metrics":
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
