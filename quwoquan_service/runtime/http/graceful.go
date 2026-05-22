package runtimehttp

import (
	"context"
	"log"
	"net/http"
	"os/signal"
	"syscall"
	"time"
)

// ListenAndServeGraceful starts server and blocks until SIGINT/SIGTERM,
// then initiates graceful shutdown with the given timeout.
func ListenAndServeGraceful(server *http.Server, shutdownTimeout time.Duration) error {
	signalCtx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	errCh := make(chan error, 1)
	go func() {
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			errCh <- err
		}
		close(errCh)
	}()

	select {
	case err := <-errCh:
		if err != nil {
			return err
		}
		return nil
	case <-signalCtx.Done():
		log.Printf("received shutdown signal, draining with timeout=%v", shutdownTimeout)
	}

	shutdownCtx, cancel := context.WithTimeout(context.Background(), shutdownTimeout)
	defer cancel()
	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Printf("WARN: graceful shutdown failed: %v; forcing close", err)
		_ = server.Close()
		return err
	}
	log.Println("graceful shutdown complete")
	return nil
}
