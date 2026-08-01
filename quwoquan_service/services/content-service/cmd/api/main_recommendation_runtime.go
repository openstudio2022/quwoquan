package main

import (
	"log"
	"log/slog"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	deliveryapp "quwoquan_service/services/content-service/internal/content/feed_delivery_page/application"
	deliveryrecommendation "quwoquan_service/services/content-service/internal/content/feed_delivery_page/infrastructure/recommendation"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func buildRankedRecommendationGateway(
	cfg config,
) deliveryapp.RankedRecommendationGateway {
	if !cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "" {
		log.Fatal("content-service requires recommendation-service ranked page endpoint")
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("ranked recommendation service auth config invalid: %v", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"recommendation.ranked_page"},
	)
	if err != nil {
		log.Fatalf("ranked recommendation service credentials invalid: %v", err)
	}
	client, err := deliveryrecommendation.NewHTTPClient(
		cfg.RecModelService.URL,
		credentials,
	)
	if err != nil {
		log.Fatalf("ranked recommendation service client invalid: %v", err)
	}
	return client
}

// buildRecommendationSignalRuntime keeps the read cache and buffered write
// path on one HotPath so their subject-closure policy cannot drift.
func buildRecommendationSignalRuntime(
	router *rtredis.Router,
	subjectClosureGuard rtrec.SubjectClosureGuard,
	logger *slog.Logger,
	feedConfig feedRuntimeConfig,
) (*rtrec.SessionCache, *rtrec.BufferedHotPath) {
	hotPath := rtrec.NewHotPath(
		rtredis.NewRecAdapter(router.Scene("rec")),
		rtrec.WithSubjectClosureGuard(subjectClosureGuard),
		rtrec.WithRankedFeedWindowQuotaPolicy(
			feedConfig.rankedWindowQuotaPolicy(),
		),
	)
	return rtrec.NewSessionCache(hotPath, 2*time.Second, 10000),
		rtrec.NewBufferedHotPath(hotPath, rtrec.WithBufferLogger(logger))
}

// composeRecommendationModelScorer 校验商用环境的模型依赖并装配生产 scorer。
func composeRecommendationModelScorer(
	cfg config,
	appEnv string,
	logger *slog.Logger,
	recOpts []rtrec.EngineOption,
) []rtrec.EngineOption {
	if (appEnv == "beta" || appEnv == "gamma" || appEnv == "prod") &&
		(!cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "") {
		log.Fatalf("recommendation service is required in APP_ENV=%s", appEnv)
	}
	if cfg.RecModelService.Enabled && cfg.RecModelService.URL != "" {
		timeout := time.Duration(cfg.RecModelService.TimeoutMs) * time.Millisecond
		if timeout <= 0 {
			timeout = 50 * time.Millisecond
		}
		modelTokenConfig, err := rtauth.LoadAccessTokenConfig(
			runtimeconfig.EnvRuntimeConfigProvider{},
		)
		if err != nil {
			log.Fatalf("recommendation service auth config invalid: %v", err)
		}
		modelCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			modelTokenConfig,
			"content-service",
			[]string{"recommendation.model.score"},
		)
		if err != nil {
			log.Fatalf("recommendation service credentials invalid: %v", err)
		}
		client, err := recinfra.NewHTTPModelServiceClient(
			cfg.RecModelService.URL,
			timeout,
			modelCredentials,
		)
		if err != nil {
			log.Fatalf("recommendation service client invalid: %v", err)
		}
		recOpts = append(recOpts, rtrec.WithScorer(newProductionScorer(client, timeout, logger)))
		log.Printf("content-service recommendation-service enabled url=%s timeout=%v scorer=cascade(remote->rule)", cfg.RecModelService.URL, timeout)
	}
	return recOpts
}
