package main

import (
	"context"
	"log"
	"os"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/alerting"
	telemetrypersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

// startTelemetryAlertLoop 装配 ES 聚合告警评估循环。
// policy_path 与 alertmanager_url 均非空才启动；配置存在但内容非法时
// fail-fast，禁止带着损坏的告警策略静默运行。
func startTelemetryAlertLoop(
	ctx context.Context,
	cfg config,
	store *telemetrypersistence.ElasticsearchEventLogStore,
) {
	policyPath := strings.TrimSpace(cfg.TelemetryAlerts.PolicyPath)
	alertmanagerURL := strings.TrimSpace(cfg.TelemetryAlerts.AlertmanagerURL)
	if policyPath == "" && alertmanagerURL == "" {
		log.Printf("product-ops-service telemetry alert loop disabled: no policy configured")
		return
	}
	if policyPath == "" || alertmanagerURL == "" {
		log.Fatalf(
			"product-ops-service telemetry alert loop misconfigured: policy_path and alertmanager_url must both be set",
		)
	}
	raw, err := os.ReadFile(policyPath)
	if err != nil {
		log.Fatalf("product-ops-service telemetry alert policy unreadable: %v", err)
	}
	policy, err := application.ParseAlertPolicy(raw)
	if err != nil {
		log.Fatalf("product-ops-service telemetry alert policy invalid: %v", err)
	}
	notifier, err := alerting.NewAlertmanagerClient(alertmanagerURL, 10*time.Second)
	if err != nil {
		log.Fatalf("product-ops-service Alertmanager client invalid: %v", err)
	}
	loop, err := application.NewAlertEvaluationLoop(
		policy,
		store,
		notifier,
		store,
		time.Duration(cfg.TelemetryAlerts.IntervalMS)*time.Millisecond,
	)
	if err != nil {
		log.Fatalf("product-ops-service telemetry alert loop invalid: %v", err)
	}
	go loop.Run(ctx)
	log.Printf(
		"product-ops-service telemetry alert loop started: policy=%s alerts=%d alertmanager=%s",
		policy.Name, len(policy.Alerts), alertmanagerURL,
	)
}
