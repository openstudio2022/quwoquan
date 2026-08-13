package bootstrap

import (
	"fmt"
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
	postports "quwoquan_service/services/content-service/internal/content/post/application/ports"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
)

func buildRankedRecommendationGateway(
	cfg config,
) (deliveryapp.RankedRecommendationGateway, error) {
	if !cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "" {
		return nil, fmt.Errorf("content-service requires recommendation-service ranked page endpoint")
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return nil, fmt.Errorf("ranked recommendation service auth config invalid: %w", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"recommendation.ranked_page"},
	)
	if err != nil {
		return nil, fmt.Errorf("ranked recommendation service credentials invalid: %w", err)
	}
	client, err := deliveryrecommendation.NewHTTPClient(
		cfg.RecModelService.URL,
		credentials,
	)
	if err != nil {
		return nil, fmt.Errorf("ranked recommendation service client invalid: %w", err)
	}
	return client, nil
}

func buildAuthorImpactProjectionReader(cfg config) (postports.AuthorImpactProjectionReader, error) {
	if !cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "" {
		return nil, fmt.Errorf("content-service requires recommendation-service feature profile reader")
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("recommendation feature profile auth config invalid: %w", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"recommendation.feature_profile.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation feature profile credentials invalid: %w", err)
	}
	client, err := recinfra.NewAuthorImpactReaderClient(
		cfg.RecModelService.URL,
		credentials,
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation feature profile client invalid: %w", err)
	}
	return client, nil
}

func buildGatheringSocialProofProjectionReader(
	cfg config,
) (postports.GatheringSocialProofProjectionReader, error) {
	if !cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "" {
		return nil, fmt.Errorf("content-service requires recommendation-service social proof reader")
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("recommendation social proof auth config invalid: %w", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"recommendation.feature_profile.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation social proof credentials invalid: %w", err)
	}
	client, err := recinfra.NewSocialProofReaderClient(
		cfg.RecModelService.URL,
		credentials,
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation social proof client invalid: %w", err)
	}
	return client, nil
}

func buildIntersectionProjectionReader(cfg config) (*recinfra.IntersectionReaderClient, error) {
	if !cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "" {
		return nil, fmt.Errorf("content-service requires recommendation-service intersection projection reader")
	}
	tokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("recommendation intersection projection auth config invalid: %w", err)
	}
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		tokenConfig,
		"content-service",
		[]string{"recommendation.feature_profile.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation intersection projection credentials invalid: %w", err)
	}
	client, err := recinfra.NewIntersectionReaderClient(
		cfg.RecModelService.URL,
		credentials,
	)
	if err != nil {
		return nil, fmt.Errorf("recommendation intersection projection client invalid: %w", err)
	}
	return client, nil
}

// buildRecommendationSignalRuntime keeps the read cache and buffered write
// path on one HotPath so their subject-closure policy cannot drift.
func buildRecommendationSignalRuntime(
	router *rtredis.Router,
	subjectClosureGuard rtrec.SubjectClosureGuard,
	logger *slog.Logger,
) (*rtrec.SessionCache, *rtrec.BufferedHotPath) {
	hotPath := rtrec.NewHotPath(
		rtredis.NewRecAdapter(router.Scene("rec")),
		rtrec.WithSubjectClosureGuard(subjectClosureGuard),
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
) ([]rtrec.EngineOption, error) {
	if (appEnv == "beta" || appEnv == "gamma" || appEnv == "prod") &&
		(!cfg.RecModelService.Enabled || strings.TrimSpace(cfg.RecModelService.URL) == "") {
		return nil, fmt.Errorf("recommendation service is required in APP_ENV=%s", appEnv)
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
			return nil, fmt.Errorf("recommendation service auth config invalid: %w", err)
		}
		modelCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			modelTokenConfig,
			"content-service",
			[]string{"recommendation.model.score"},
		)
		if err != nil {
			return nil, fmt.Errorf("recommendation service credentials invalid: %w", err)
		}
		client, err := recinfra.NewHTTPModelServiceClient(
			cfg.RecModelService.URL,
			timeout,
			modelCredentials,
		)
		if err != nil {
			return nil, fmt.Errorf("recommendation service client invalid: %w", err)
		}
		recOpts = append(recOpts, rtrec.WithScorer(newProductionScorer(client, timeout, logger)))
		log.Printf("content-service recommendation-service enabled url=%s timeout=%v scorer=cascade(remote->rule)", cfg.RecModelService.URL, timeout)
	}
	return recOpts, nil
}
