package main

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	rtredis "quwoquan_service/runtime/redis"
)

func main() {
	if err := run(); err != nil {
		logStartupFailure(err)
		os.Exit(1)
	}
}

func run() (resultErr error) {
	runtime, err := bootstrapAssistantAPIRuntime()
	if err != nil {
		return err
	}
	defer runtime.Close()

	infrastructure, err := bootstrapAssistantInfrastructure(runtime)
	if err != nil {
		return err
	}
	defer infrastructure.Close()

	assistant, err := wireAssistantRuntime(runtime, infrastructure)
	if err != nil {
		return err
	}

	workers, err := startAssistantBackgroundWorkers(
		runtime,
		infrastructure,
		assistant,
	)
	if err != nil {
		return err
	}
	defer func() {
		resultErr = errors.Join(resultErr, workers.Close())
	}()

	return serveAssistantHTTP(runtime, infrastructure, assistant)
}

func logStartupFailure(err error) {
	logger := slog.New(slog.NewJSONHandler(os.Stderr, nil))
	attributes := []any{
		"service", "assistant-service",
		"error", err.Error(),
	}
	var dependencyFailure *startupDependencyError
	if errors.As(err, &dependencyFailure) {
		attributes = append(
			attributes,
			"dependency", dependencyFailure.Dependency,
			"stage", dependencyFailure.Stage,
		)
	}
	logger.Error("assistant-service startup failed", attributes...)
}

func buildAccountSecurityAuthority(
	cfg config,
	accessTokenConfig rtauth.TokenConfig,
) (*rtauth.HTTPAccountSecurityAuthority, error) {
	accountSecurityAuthorityCredentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		accessTokenConfig,
		"assistant-service",
		[]string{"user.account.security.read"},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority credential init failed: %w", err)
	}
	accountSecurityAuthorityTimeout := time.Duration(
		cfg.AccountSecurityAuthority.TimeoutMs,
	) * time.Millisecond
	accountSecurityAuthority, err := rtauth.NewHTTPAccountSecurityAuthority(
		rtauth.HTTPAccountSecurityAuthorityConfig{
			BaseURL:     cfg.AccountSecurityAuthority.BaseURL,
			HTTPClient:  &http.Client{Timeout: accountSecurityAuthorityTimeout},
			Credentials: accountSecurityAuthorityCredentials,
			Timeout:     accountSecurityAuthorityTimeout,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("account security authority config invalid: %w", err)
	}
	return accountSecurityAuthority, nil
}

func registerAccountSecurityAuthorityHealth(
	healthChecker *rthealth.Checker,
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority,
	router *rtredis.Router,
) {
	healthChecker.Register("account_security_authority", func(hctx context.Context) error {
		return accountSecurityAuthority.CheckAccountSecurityAuthority(hctx)
	})
	healthChecker.Register("redis", func(ctx context.Context) error {
		return router.PingAll(ctx)
	})
}

func withAssistantAccessMiddleware(
	handler http.Handler,
	accessVerifier *rtauth.Verifier,
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority,
) http.Handler {
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      accessVerifier,
		AccountSecurityAuthority: accountSecurityAuthority,
	})(handler)
}
