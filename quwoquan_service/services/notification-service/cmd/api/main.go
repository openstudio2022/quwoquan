package main

import (
	"context"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	"quwoquan_service/runtime/reliabletask"
	httpadapter "quwoquan_service/services/notification-service/internal/adapters/http"
	"quwoquan_service/services/notification-service/internal/application"
)

func main() {
	ctx := context.Background()
	store := reliabletask.NewMemoryStore()
	_ = prometheus.Register(reliabletask.NewMetricsCollector(store))
	service := application.NewNotificationDeliveryService(
		store,
		application.NoopDeliveryAdapter{},
		reliabletask.RateLimitPolicy{ClaimPerSecond: 100, DispatchPerSecond: 100, RetryPerSecond: 20},
	)
	go runWorkerLoop(ctx, service)

	rootMux := http.NewServeMux()
	rootMux.Handle("/", httpadapter.NewHandler(service).Routes())
	rootMux.Handle("/metrics", rtmetrics.Handler())
	addr := getenvOrDefault("NOTIFICATION_SERVICE_ADDR", ":18087")
	server := &http.Server{
		Addr:              addr,
		Handler:           rootMux,
		BaseContext:       func(_ net.Listener) context.Context { return ctx },
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("notification-service listening on %s", server.Addr)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("notification-service: %v", err)
	}
}

func runWorkerLoop(ctx context.Context, service *application.NotificationDeliveryService) {
	ticker := time.NewTicker(500 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			for i := 0; i < 100; i++ {
				processed, err := service.ProcessOne(ctx)
				if err != nil {
					log.Printf("notification delivery worker failed: %v", err)
					break
				}
				if !processed {
					break
				}
			}
		}
	}
}

func getenvOrDefault(key string, fallback string) string {
	if value := strings.TrimSpace(os.Getenv(key)); value != "" {
		return value
	}
	return fallback
}
