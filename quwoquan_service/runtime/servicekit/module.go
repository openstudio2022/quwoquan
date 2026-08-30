package servicekit

import (
	"context"
	"errors"
	"fmt"
	"log"
	"net"
	"net/http"
	"strings"
	"sync"
	"sync/atomic"
	"time"

	rterr "quwoquan_service/runtime/errors"
	rthealth "quwoquan_service/runtime/health"
	"quwoquan_service/runtime/servicehost"
)

// WorkerRegistry 收集模块启动后由 Start 相位统一拉起的后台 worker。
type WorkerRegistry struct {
	starts    []func(context.Context)
	fallibles []fallibleWorker
}

// fallibleWorker 是「启动动作本身可失败」的 worker：start 拉起内部循环后
// 立即返回，返回值表达拉起是否成功。它不是长跑循环体。
type fallibleWorker struct {
	name  string
	start func(context.Context) error
}

// Add 注册一个 worker 启动函数；nil 被忽略。函数在独立 goroutine 中长跑，
// 直到模块 context 取消。
func (registry *WorkerRegistry) Add(start func(context.Context)) {
	if start != nil {
		registry.starts = append(registry.starts, start)
	}
}

// AddFallible 注册一个启动可失败的 worker。它在 Start 相位按注册顺序**同步**
// 执行，任一失败即让 Start 失败，进程不会进入 Ready 窗口也不会开放 admission。
// 用于 scheduler 一类「拉起时就能判定成败」的 worker：把这种失败降级成健康
// 检查会让失败时机推迟到 Ready 窗口，也让「拉起失败」与「运行中故障」共用
// 同一个信号。长跑循环体仍用 Add。
func (registry *WorkerRegistry) AddFallible(name string, start func(context.Context) error) {
	if start == nil {
		return
	}
	registry.fallibles = append(registry.fallibles, fallibleWorker{name: name, start: start})
}

// CleanupStack 收集资源释放函数，Shutdown 相位逆序执行。
type CleanupStack struct {
	entries []func(context.Context) error
}

// Add 注册一个清理函数；nil 被忽略。
func (stack *CleanupStack) Add(cleanup func(context.Context) error) {
	if cleanup != nil {
		stack.entries = append(stack.entries, cleanup)
	}
}

// Close 逆序执行全部清理函数并聚合错误；幂等。
func (stack *CleanupStack) Close(ctx context.Context) error {
	var result error
	for index := len(stack.entries) - 1; index >= 0; index-- {
		result = errors.Join(result, stack.entries[index](ctx))
	}
	stack.entries = nil
	return result
}

// ModuleSpec 声明一个 servicehost.Module 的通用生命周期输入。
// 领域装配（对象仓储、consumer、路由）仍由各服务 bootstrap 完成，
// 这里只接收装配结果。
type ModuleSpec struct {
	Identity Identity
	// ListenAddr 是环境装配注入的监听地址；缺失即 fail-closed，
	// servicekit 不提供魔法默认端口。
	ListenAddr string
	// ConfigDigest 是本模块生效配置快照的版本 digest。
	ConfigDigest string
	// Handler 是已完成观测/鉴权包装的最终 HTTP handler。
	Handler http.Handler
	// Timeouts 来自契约派生的服务器超时（AuthStack.Timeouts）。
	Timeouts HTTPServerTimeouts
	Health   *rthealth.Checker
	Workers  *WorkerRegistry
	Cleanups *CleanupStack
	// PrepareMigration 可选；用于 servicehost PrepareMigration 相位。
	PrepareMigration func(context.Context) error
	// ReadinessTimeout 限定 Ready 相位健康收敛时长；零值取 15s。
	ReadinessTimeout time.Duration
	// PreAdmissionPaths 是 OpenAdmission 之前即放行的内部端点，见
	// Module.admissionHandler 的判据说明。
	PreAdmissionPaths []string
}

// HTTPServerTimeouts 是服务器超时的本包投影，避免调用方在未装配 auth 栈时
// 依赖 rtauth 类型。
type HTTPServerTimeouts struct {
	ReadHeader time.Duration
	Write      time.Duration
	Idle       time.Duration
}

// Module 是通用 servicehost.Module 实现：监听绑定、worker 编组、健康就绪、
// admission 门与逆序清理。
type Module struct {
	name              string
	appEnv            string
	configDigest      string
	server            *http.Server
	health            *rthealth.Checker
	listener          net.Listener
	admission         atomic.Bool
	preAdmissionPaths map[string]bool
	serveError        chan error
	readinessTimeout  time.Duration

	workerStarts     []func(context.Context)
	fallibleWorkers  []fallibleWorker
	workerCancel     context.CancelFunc
	workerGroup      sync.WaitGroup
	runContext       context.Context
	prepareMigration func(context.Context) error
	cleanup          func(context.Context) error
}

var _ servicehost.Module = (*Module)(nil)

// NewModule 校验 spec 并构造通用模块。所有必填项缺失都在此 fail-closed，
// 不进入 servicehost 相位机。
func NewModule(spec ModuleSpec) (*Module, error) {
	serviceName := spec.Identity.ServiceName
	if serviceName == "" {
		return nil, errors.New("module spec requires a resolved identity")
	}
	if spec.ListenAddr == "" {
		return nil, fmt.Errorf("%s listen address is required (no default port)", serviceName)
	}
	if spec.ConfigDigest == "" {
		return nil, fmt.Errorf("%s config digest is required", serviceName)
	}
	if spec.Handler == nil {
		return nil, fmt.Errorf("%s HTTP handler is required", serviceName)
	}
	if spec.Health == nil {
		return nil, fmt.Errorf("%s health checker is required", serviceName)
	}
	// Workers 注册器必填以强制 bootstrap 声明 worker 注册点；零个 worker 是
	// 纯 HTTP 服务的合法形态。
	if spec.Workers == nil {
		return nil, fmt.Errorf("%s worker registry is required", serviceName)
	}
	if spec.Cleanups == nil {
		return nil, fmt.Errorf("%s cleanup stack is required", serviceName)
	}
	readinessTimeout := spec.ReadinessTimeout
	if readinessTimeout <= 0 {
		readinessTimeout = 15 * time.Second
	}
	preAdmissionPaths, err := normalizePreAdmissionPaths(serviceName, spec.PreAdmissionPaths)
	if err != nil {
		return nil, err
	}
	module := &Module{
		name:              serviceName,
		appEnv:            spec.Identity.AppEnv,
		configDigest:      spec.ConfigDigest,
		health:            spec.Health,
		preAdmissionPaths: preAdmissionPaths,
		serveError:        make(chan error, 1),
		readinessTimeout:  readinessTimeout,
		workerStarts:      spec.Workers.starts,
		fallibleWorkers:   spec.Workers.fallibles,
		prepareMigration:  spec.PrepareMigration,
		cleanup:           spec.Cleanups.Close,
	}
	module.server = &http.Server{
		Addr:              spec.ListenAddr,
		Handler:           module.admissionHandler(spec.Handler),
		ReadHeaderTimeout: spec.Timeouts.ReadHeader,
		WriteTimeout:      spec.Timeouts.Write,
		IdleTimeout:       spec.Timeouts.Idle,
	}
	module.server.BaseContext = func(net.Listener) context.Context {
		if module.runContext != nil {
			return module.runContext
		}
		return context.Background()
	}
	return module, nil
}

func (module *Module) Name() string {
	if module == nil {
		return ""
	}
	return module.name
}

func (module *Module) ConfigDigest() string {
	if module == nil {
		return ""
	}
	return module.configDigest
}

func (module *Module) ValidateConfig(context.Context) error {
	if module == nil || module.server == nil || module.health == nil || module.cleanup == nil {
		return fmt.Errorf("%s module is incomplete", module.Name())
	}
	return nil
}

func (module *Module) PrepareMigration(ctx context.Context) error {
	if module.prepareMigration == nil {
		return nil
	}
	return module.prepareMigration(ctx)
}

func (module *Module) Bind(context.Context) error {
	if module == nil || module.server == nil {
		return fmt.Errorf("%s HTTP server is unavailable", module.Name())
	}
	listener, err := net.Listen("tcp", module.server.Addr)
	if err != nil {
		return fmt.Errorf("%s listener bind: %w", module.name, err)
	}
	module.listener = listener
	return nil
}

func (module *Module) Start(ctx context.Context) error {
	if module == nil || module.listener == nil {
		return fmt.Errorf("%s listener is not bound", module.Name())
	}
	if err := ctx.Err(); err != nil {
		return fmt.Errorf("%s start context: %w", module.name, err)
	}
	module.runContext, module.workerCancel = context.WithCancel(ctx)
	// 可失败 worker 先同步拉起：失败在 Start 相位即暴露，Supervisor 不会
	// 进入 Ready 也不会开放 admission。
	for _, worker := range module.fallibleWorkers {
		if err := worker.start(module.runContext); err != nil {
			return fmt.Errorf("%s worker %s start failed: %w", module.name, worker.name, err)
		}
	}
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
	log.Printf("%s listening on %s (env=%s)", module.name, module.server.Addr, module.appEnv)
	return nil
}

func (module *Module) Ready(ctx context.Context) error {
	readinessCtx, cancel := context.WithTimeout(ctx, module.readinessTimeout)
	defer cancel()
	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()

	var failedChecks []string
	for {
		select {
		case err := <-module.serveError:
			return fmt.Errorf("%s listener failed: %w", module.name, err)
		default:
		}
		result := module.health.Check(readinessCtx)
		failedChecks = result.FailedChecks
		if result.Status == "ok" {
			select {
			case err := <-module.serveError:
				return fmt.Errorf("%s listener failed: %w", module.name, err)
			default:
				return nil
			}
		}
		select {
		case err := <-module.serveError:
			return fmt.Errorf("%s listener failed: %w", module.name, err)
		case <-readinessCtx.Done():
			return fmt.Errorf(
				"%s readiness failed: %v: %w",
				module.name,
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

// normalizePreAdmissionPaths 校验并归一化 admission 前置放行清单。
//
// 放行清单绕过 admission 门，因此判据必须窄：只允许 `/internal/` 前缀的精确
// 路径。它的唯一正当用途是打破 service-core 单进程内的启动循环——同进程另一
// 个模块的就绪检查要调用本模块的内部端点，而本模块此刻尚未 OpenAdmission，
// 双方互等即死锁。业务路由一旦进入这个清单，等于在就绪之前接受真实流量。
func normalizePreAdmissionPaths(serviceName string, paths []string) (map[string]bool, error) {
	if len(paths) == 0 {
		return nil, nil
	}
	normalized := make(map[string]bool, len(paths))
	for _, path := range paths {
		trimmed := strings.TrimSpace(path)
		if !strings.HasPrefix(trimmed, "/internal/") {
			return nil, fmt.Errorf(
				"%s pre-admission path %q must be an exact /internal/ path",
				serviceName, path,
			)
		}
		if strings.Contains(trimmed, "*") || strings.HasSuffix(trimmed, "/") {
			return nil, fmt.Errorf(
				"%s pre-admission path %q must not be a prefix or wildcard pattern",
				serviceName, path,
			)
		}
		normalized[trimmed] = true
	}
	return normalized, nil
}

// admissionHandler 在 OpenAdmission 之前拒绝业务流量；探针与抓取端点
// （/healthz、/readyz、/metrics）以及声明的 pre-admission 内部端点始终放行。
func (module *Module) admissionHandler(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		switch request.URL.Path {
		case "/healthz", "/readyz", "/metrics":
			next.ServeHTTP(writer, request)
			return
		}
		// `/readyz/` 下是就绪命名空间：领域专属就绪子路由（如配置收敛面）与
		// 骨架 /readyz 同属「回答本实例是否可接流量」。把它们挡在 admission
		// 门后是自指的——那会让「查询就绪状态」这个动作本身先要求已就绪，
		// 于是发布编排在启动窗口里只能拿到 503 而分辨不出未就绪与故障。
		if strings.HasPrefix(request.URL.Path, "/readyz/") {
			next.ServeHTTP(writer, request)
			return
		}
		if module.preAdmissionPaths[request.URL.Path] {
			next.ServeHTTP(writer, request)
			return
		}
		if !module.admission.Load() {
			rterr.WriteHTTPError(
				writer,
				rterr.NewAppError(
					rterr.NewCode(rterr.ModuleGateway, rterr.KindMiddleware, "upstream_unavailable"),
					"服务暂不可用，请稍后重试",
					"service admission is not ready",
				).WithMetadata("upstream_unavailable", http.StatusServiceUnavailable).
					WithRecoveryDirective("retry", "snackbar", 1),
				rterr.HTTPWriteOptionsFromRequest(request),
			)
			return
		}
		next.ServeHTTP(writer, request)
	})
}
