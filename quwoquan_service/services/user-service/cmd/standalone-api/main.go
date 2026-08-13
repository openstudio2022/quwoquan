package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"quwoquan_service/runtime/servicehost"
	bootstrap "quwoquan_service/services/user-service/cmd/api"
)

func main() {
	if err := run(); err != nil {
		slog.Error("user-service stopped with failure", "error", err)
		os.Exit(1)
	}
}

func run() error {
	module, err := bootstrap.NewModule()
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
