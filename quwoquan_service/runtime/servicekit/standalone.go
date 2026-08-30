package servicekit

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"quwoquan_service/runtime/servicehost"
)

// RunStandalone 是各服务 cmd/standalone-api 的唯一入口壳：构造模块、交给
// servicehost 相位机运行、监听中断信号并限时优雅退出。失败以非零码结束进程。
func RunStandalone(serviceName string, newModule func() (servicehost.Module, error)) {
	if err := runStandalone(newModule); err != nil {
		slog.Error(serviceName+" stopped with failure", "error", err)
		os.Exit(1)
	}
}

func runStandalone(newModule func() (servicehost.Module, error)) error {
	module, err := newModule()
	if err != nil {
		return err
	}
	host, err := servicehost.NewSupervisor(module)
	if err != nil {
		return err
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	if err := host.Start(ctx); err != nil {
		return err
	}
	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	return host.Shutdown(shutdownCtx)
}
