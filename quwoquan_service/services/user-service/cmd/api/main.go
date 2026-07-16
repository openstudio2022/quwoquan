package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"gopkg.in/yaml.v3"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"
	"quwoquan_service/runtime/otpseal"

	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	personaapp "quwoquan_service/services/user-service/internal/application/persona/persona"
	proposalapp "quwoquan_service/services/user-service/internal/application/persona/profile_update_proposal"
	relationshipapp "quwoquan_service/services/user-service/internal/application/relationship/persona_relationship"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	userintegration "quwoquan_service/services/user-service/internal/infrastructure/integration"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	personapersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/persona/persistence"
	proposalpersistence "quwoquan_service/services/user-service/internal/infrastructure/persona/profile_update_proposal/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
	relationshippersistence "quwoquan_service/services/user-service/internal/infrastructure/relationship/persona_relationship/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/searchindex"
	"quwoquan_service/services/user-service/internal/infrastructure/tagindex"
)

type redisSceneCfg struct {
	Mode     string   `yaml:"mode"`
	Addr     string   `yaml:"addr"`
	Addrs    []string `yaml:"addrs"`
	Password string   `yaml:"password"`
	DB       int      `yaml:"db"`
	TLS      bool     `yaml:"tls"`
	Pool     struct {
		Size           int `yaml:"size"`
		MinIdle        int `yaml:"min_idle"`
		ReadTimeoutMs  int `yaml:"read_timeout_ms"`
		WriteTimeoutMs int `yaml:"write_timeout_ms"`
		DialTimeoutMs  int `yaml:"dial_timeout_ms"`
	} `yaml:"pool"`
}

type config struct {
	Config struct {
		Version         string `yaml:"version"`
		MinImageVersion string `yaml:"min_image_version"`
		MaxImageVersion string `yaml:"max_image_version"`
	} `yaml:"config"`
	Service struct {
		HTTP struct {
			Addr string `yaml:"addr"`
		} `yaml:"http"`
	} `yaml:"service"`
	Postgres struct {
		DSN                    string `yaml:"dsn"`
		MaxOpenConns           int    `yaml:"max_open_conns"`
		MaxIdleConns           int    `yaml:"max_idle_conns"`
		ConnMaxLifetimeMinutes int    `yaml:"conn_max_lifetime_minutes"`
	} `yaml:"postgres"`
	MongoDB struct {
		URI      string `yaml:"uri"`
		Database string `yaml:"database"`
	} `yaml:"mongodb"`
	ES    searchindex.ESConfig `yaml:"es"`
	Redis struct {
		General  redisSceneCfg `yaml:"general"`
		Realtime redisSceneCfg `yaml:"realtime"`
	} `yaml:"redis"`
	Integration struct {
		ExternalInteractionBaseURL string `yaml:"external_interaction_base_url"`
		Social                     struct {
			Providers map[string]providerOAuthCfg `yaml:"providers"`
		} `yaml:"social"`
		OneTap struct {
			Resolver string `yaml:"resolver"`
		} `yaml:"one_tap"`
		OTP struct {
			Mode string `yaml:"mode"`
		} `yaml:"otp"`
	} `yaml:"integration"`
}

type providerOAuthCfg struct {
	AppID                string `yaml:"app_id"`
	AppSecret            string `yaml:"app_secret"`
	AppPrivateKeyPEM     string `yaml:"app_private_key_pem"`
	PlatformPublicKeyPEM string `yaml:"platform_public_key_pem"`
	MerchantPID          string `yaml:"merchant_pid"`
	TokenURL             string `yaml:"token_url"`
	UserInfoURL          string `yaml:"user_info_url"`
}

func main() {
	serviceName, appEnv, configRoot, configVersion, imageVersion, err := resolveRuntimeIdentity()
	if err != nil {
		log.Fatalf("user-service runtime identity invalid: %v", err)
	}
	cfg, err := loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
	if err != nil {
		log.Fatalf("user-service config load failed: %v", err)
	}
	applyEnvOverrides(&cfg)
	if err := validateRuntimeCompatibility(cfg, configVersion, imageVersion); err != nil {
		log.Fatalf("user-service config compatibility failed: %v", err)
	}

	ctx := context.Background()

	otelShutdown := rtotel.MustInit(rtotel.Config{ServiceName: "user-service", SamplingRatio: 0.1})
	defer otelShutdown()

	addr := getenvOrDefault("USER_SERVICE_ADDR", cfg.Service.HTTP.Addr)
	if addr == "" {
		addr = ":18081"
	}

	// 1. PostgreSQL
	poolCfg, err := pgxpool.ParseConfig(cfg.Postgres.DSN)
	if err != nil {
		log.Fatalf("postgres parse config: %v", err)
	}
	if cfg.Postgres.MaxOpenConns > 0 {
		poolCfg.MaxConns = int32(cfg.Postgres.MaxOpenConns)
	}
	if cfg.Postgres.MaxIdleConns > 0 {
		poolCfg.MinConns = int32(cfg.Postgres.MaxIdleConns)
	}
	if cfg.Postgres.ConnMaxLifetimeMinutes > 0 {
		poolCfg.MaxConnLifetime = time.Duration(cfg.Postgres.ConnMaxLifetimeMinutes) * time.Minute
	}
	pgPool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		log.Fatalf("postgres connect: %v", err)
	}
	defer pgPool.Close()
	if err := pgPool.Ping(ctx); err != nil {
		log.Fatalf("postgres ping: %v", err)
	}

	// 2. Run startup migrations with a persisted ledger so restart/rollout can
	// safely keep the existing Postgres volume.
	if err := persistence.RunManagedMigrations(ctx, pgPool); err != nil {
		log.Fatalf("migration: %v", err)
	}

	// 3. MongoDB
	var mongoClient *mongo.Client
	var mongoDB *mongo.Database
	if cfg.MongoDB.URI != "" {
		mongoClient = rtmongo.MustConnect(ctx, rtmongo.ConnectConfig{URI: cfg.MongoDB.URI}, "user-service")
		dbName := cfg.MongoDB.Database
		if dbName == "" {
			dbName = "quwoquan"
		}
		mongoDB = mongoClient.Database(dbName)
	}
	defer func() {
		if mongoClient != nil {
			_ = mongoClient.Disconnect(ctx)
		}
	}()

	// 4. Redis
	redisRouter := buildRedisRouter(cfg)
	defer redisRouter.Close()
	if err := redisRouter.PingAll(ctx); err != nil {
		log.Printf("WARN: user-service redis ping: %v", err)
	}
	redisClient := redisRouter.Scene("general")

	shardDirectory, err := application.LoadDefaultShardDirectory()
	if err != nil {
		log.Fatalf("load shard directory: %v", err)
	}

	// 5. Stores
	profileStore := persistence.NewPgProfileStore(pgPool)
	personaStore := persistence.NewPgPersonaStore(pgPool).WithMongoDatabase(mongoDB)
	settingStore := persistence.NewPgSettingStore(pgPool)
	relationshipStore := relationshippersistence.NewPgPersonaRelationshipStore(pgPool)
	greetingStore := persistence.NewPgGreetingStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	userAuthStore := persistence.NewPgUserAuthStore(pgPool)
	userDeviceStore := persistence.NewPgUserDeviceStore(pgPool)
	consentRecordStore := persistence.NewPgConsentRecordStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
	profileQrTokenStore := persistence.NewPgProfileQrTokenStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)
	personaProfileProposalStore, err := personapersistence.NewProfileProposalPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("Persona profile proposal Store init failed: %v", err)
	}
	profileProposalStore, err := proposalpersistence.NewPostgresStore(pgPool)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Store init failed: %v", err)
	}

	// 5b. Search index (ES) — write side of user.search_index_worker. Disabled
	// (no-op) unless es.enabled / SEARCH_ES_* are set, so the primary write path
	// is unaffected in alpha and any env without the shared cluster.
	searchindex.ApplyESEnvOverrides(&cfg.ES)
	searchBuilt, err := searchindex.Build(cfg.ES, profileStore)
	if err != nil {
		log.Fatalf("user-service search index build failed: %v", err)
	}
	if searchBuilt.Client != nil {
		if err := searchBuilt.EnsureIndex(ctx); err != nil {
			log.Fatalf("user-service search index ensure failed: %v", err)
		}
		log.Printf("user-service search index enabled: %s", searchBuilt.Client.IndexName())
	}

	// 6. Caches
	profileCache := cache.NewProfileCache(redisClient)
	settingCache := cache.NewSettingCache(redisClient)
	// The domain MQ publisher stays the primary; when ES is enabled the search
	// projector is composed onto the fan-out tail (best-effort, never blocks).
	relationshipEventPublisher := mq.NewEventPublisher(redisClient)
	var userEventPublisher application.UserEventPublisher = relationshipEventPublisher
	if searchBuilt.Projector != nil {
		userEventPublisher = searchindex.ComposePublisher(userEventPublisher, searchBuilt.Projector)
	}
	if mongoDB != nil {
		userEventPublisher = searchindex.ComposePublisher(
			userEventPublisher,
			tagindex.NewProjector(mongoDB.Collection("object_tag_index"), profileStore),
		)
	}
	userSyncService := runtimesync.NewService(redisClient, redisRouter.Scene("realtime"))

	// 7. Services
	var regionTagResolver application.RegionTagResolver = application.PathRegionTagResolver{}
	var profileTagValidator application.ProfileTagValidator = application.PathProfileTagValidator{}
	if tagServiceBaseURL := getenvOrDefault("TAG_SERVICE_BASE_URL", ""); tagServiceBaseURL != "" {
		regionTagResolver = userintegration.NewTagServiceRegionResolver(tagServiceBaseURL, nil)
		profileTagValidator = userintegration.NewTagServiceProfileTagValidator(tagServiceBaseURL, nil)
	}
	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		settingStore,
		profileCache,
		userEventPublisher,
		userSyncService,
		application.WithProfileQrTokenStore(profileQrTokenStore),
		application.WithRegionTagResolver(regionTagResolver),
		application.WithProfileTagValidator(profileTagValidator),
	)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	relationshipService := relationshipapp.NewPersonaRelationshipService(
		relationshipStore,
		profileStore,
		personaStore,
		profileCache,
		greetingStore,
	)
	relationshipOutboxRelay := relationshipapp.NewOutboxRelay(relationshipStore, relationshipEventPublisher)
	go func() {
		if err := relationshipOutboxRelay.Run(ctx, time.Second); err != nil && ctx.Err() == nil {
			log.Printf("ERROR: persona relationship outbox relay stopped: %v", err)
		}
	}()
	chatServiceBaseURL := strings.TrimSpace(getenvOrDefault("CHAT_SERVICE_BASE_URL", ""))
	if chatServiceBaseURL == "" {
		log.Fatal("user-service startup failed: CHAT_SERVICE_BASE_URL is required")
	}
	conversationGateway := userintegration.NewChatServiceClient(chatServiceBaseURL, nil)
	greetingService := application.NewGreetingService(
		greetingStore,
		relationshipService,
		conversationGateway,
		userEventPublisher,
	)
	personaService := application.NewPersonaService(personaStore, personaStore, profileCache)
	var creatorRuntimeStore *persistence.CreatorRuntimeProfileReader
	if mongoDB != nil {
		creatorRuntimeStore = persistence.NewCreatorRuntimeProfileReader(mongoDB)
	}
	workOptions := make([]application.WorkServiceOption, 0, 1)
	subAccountOptions := make([]application.SubAccountServiceOption, 0, 1)
	if creatorRuntimeStore != nil {
		workOptions = append(workOptions, application.WithCreatorRuntimeWorks(creatorRuntimeStore))
		subAccountOptions = append(
			subAccountOptions,
			application.WithCreatorRuntimeProfiles(creatorRuntimeStore),
		)
	}
	workService := application.NewWorkService(workStore, workOptions...)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	otpCodeCache := cache.NewOtpCodeCache(redisClient)
	otpChallengeStore := persistence.NewPgOtpChallengeStore(pgPool)
	socialProviderClient, err := socialAuthProviderClient(cfg)
	if err != nil {
		log.Fatalf("social auth provider client init failed: %v", err)
	}
	oneTapResolverImpl, err := oneTapResolver(cfg)
	if err != nil {
		log.Fatalf("one tap resolver init failed: %v", err)
	}
	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		log.Fatalf("access token config invalid: %v", err)
	}
	accessSigner, err := rtauth.NewHS256Signer(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token signer invalid: %v", err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		log.Fatalf("access token verifier invalid: %v", err)
	}
	otpCodeSealer, err := otpseal.LoadFromEnvironment()
	if err != nil {
		log.Fatalf("otp code reference sealer invalid: %v", err)
	}
	otpMode := configuredOTPMode(appEnv, cfg.Integration.OTP.Mode)
	otpCodeGenerator, err := otpCodeGeneratorForMode(appEnv, otpMode)
	if err != nil {
		log.Fatalf("otp mode invalid: %v", err)
	}
	externalInteractionBaseURL := getenvOrDefault("INTEGRATION_EXTERNAL_INTERACTION_BASE_URL", cfg.Integration.ExternalInteractionBaseURL)
	externalInteractionClient, err := otpExternalInteractionClientForEnvironment(
		appEnv,
		otpMode,
		externalInteractionBaseURL,
		accessSigner,
	)
	if err != nil {
		log.Fatalf("external interaction client init failed: %v", err)
	}
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		shardDirectory,
		application.WithAccountSessionStore(userAuthStore),
		application.WithDeviceRegistrationStore(userDeviceStore),
		application.WithConsentRecordStore(consentRecordStore),
		application.WithOtpCodeStore(otpCodeCache),
		application.WithOtpChallengeStore(otpChallengeStore),
		application.WithOTPCodeSealer(otpCodeSealer),
		application.WithOTPCodeGenerator(otpCodeGenerator),
		application.WithExternalInteractionClient(externalInteractionClient),
		application.WithExternalAuthProviderClient(socialProviderClient),
		application.WithOneTapPhoneResolver(oneTapResolverImpl),
		application.WithAccessTokenSigner(accessSigner),
		application.WithDefaultNicknamePrefix(getenvOrDefault("USER_DEFAULT_NICKNAME_PREFIX", "新同学")),
	)
	subAccountService := application.NewSubAccountService(
		personaStore,
		personaStore,
		personaStore,
		profileStore,
		profileCache,
		subAccountOptions...,
	)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, inviteStore)
	personaProfileProposalFacade, err := personaapp.NewProfileProposalFacade(personaProfileProposalStore)
	if err != nil {
		log.Fatalf("Persona profile proposal Facade init failed: %v", err)
	}
	profileProposalFacade, err := proposalapp.NewFacade(
		profileProposalStore,
		profileProposalStore,
		personaProfileProposalFacade,
		personaProfileProposalStore,
	)
	if err != nil {
		log.Fatalf("ProfileUpdateProposal Facade init failed: %v", err)
	}

	healthChecker := rthealth.NewChecker()
	healthChecker.Register("postgres", func(hctx context.Context) error {
		return pgPool.Ping(hctx)
	})
	healthChecker.Register("redis", func(hctx context.Context) error {
		return redisRouter.PingAll(hctx)
	})
	if mongoDB != nil {
		healthChecker.Register("mongodb", func(hctx context.Context) error {
			return mongoClient.Ping(hctx, nil)
		})
	}
	if ping := searchBuilt.HealthPing(); ping != nil {
		healthChecker.Register("search_es", ping)
	}

	// 8. Handler
	var interestReader application.InterestProfileReader
	if mongoDB != nil {
		interestReader = projection.NewMongoInterestProfileReader(mongoDB)
	}
	interestProfileService := application.NewInterestProfileService(interestReader)
	userHandler, err := httpadapter.NewUserHandler(
		profileService, searchService, relationshipService, greetingService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
		interestProfileService,
		profileProposalFacade,
	)
	if err != nil {
		log.Fatalf("user-service HTTP composition failed: %v", err)
	}
	handler := userHandler.Routes()

	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle(
		httpadapter.LoginAnonymousPath,
		rtauth.RequireGeneratedOperationAuthorizationForRoute(
			operationsecurity.ForDomain("user"),
			http.MethodPost,
			httpadapter.LoginAnonymousPath,
		)(handler),
	)
	outerMux.Handle(
		httpadapter.PullUserSyncPath,
		rtauth.RequireGeneratedOperationAuthorizationForRoute(
			operationsecurity.ForDomain("user"),
			http.MethodPost,
			httpadapter.PullUserSyncPath,
		)(handler),
	)
	outerMux.Handle(
		"/",
		rtauth.EnforceGeneratedOperationAuthorization(
			operationsecurity.ForDomain("user"),
		)(handler),
	)

	// 8.1 Observability middleware
	instanceID, _ := os.Hostname()
	ioLogger := robs.NewIOAccessLogger(os.Stdout)
	processLogger, err := robs.NewProcessTraceLogger(os.Stdout, os.Stderr, "info", nil)
	if err != nil {
		log.Fatalf("user-service process logger init failed: %v", err)
	}
	exceptionLogger, err := robs.NewExceptionLogger(os.Stdout, os.Stderr, nil)
	if err != nil {
		log.Fatalf("user-service exception logger init failed: %v", err)
	}
	observedHandler := rthttp.NewHTTPServerMiddleware(outerMux, rthttp.HTTPServerMiddlewareConfig{
		Service:           "user-service",
		ServiceName:       "user-service",
		ServiceInstanceID: instanceID,
	}, ioLogger, processLogger, exceptionLogger)
	corsHandler := rthttp.WithCORS(observedHandler, rthttp.CORSOptionsFromEnv())

	// 8.2 Interest profile projector: consume content's UserInterestRecomputed
	// and maintain the user-domain rm_user_profile_view interest read model.
	if mongoDB != nil {
		interestProjector := projection.NewInterestProfileProjector(mongoDB, nil)
		projCtx, projCancel := context.WithCancel(ctx)
		defer projCancel()
		go func() {
			if err := interestProjector.Run(projCtx, redisClient); err != nil && projCtx.Err() == nil {
				log.Printf("WARN: interest profile projector stopped: %v", err)
			}
		}()
	}

	// 9. Start
	rateLimiter := rtgov.NewRateLimiter(1000)
	rateLimited := rtgov.RateLimitMiddleware(rateLimiter)(corsHandler)
	server := &http.Server{
		Addr: addr,
		// Authentication must run before observability builds ActorContext.
		Handler: rtauth.Middleware(rtauth.MiddlewareConfig{
			AccessTokenVerifier: accessVerifier,
		})(rateLimited),
		ReadHeaderTimeout: 5 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	log.Printf("user-service listening on %s (env=%s)", addr, appEnv)
	if err := rthttp.ListenAndServeGraceful(server, 15*time.Second); err != nil {
		log.Fatalf("user-service: %v", err)
	}
}

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	serviceName = getenvOrDefault("SERVICE_NAME", "user-service")
	appEnv = getenvOrDefault("APP_ENV", "alpha")
	configRoot = os.Getenv("CONFIG_ROOT")
	configVersion = os.Getenv("CONFIG_VERSION")
	imageVersion = os.Getenv("IMAGE_VERSION")
	if !isValidAppEnv(appEnv) {
		return "", "", "", "", "", fmt.Errorf("APP_ENV must be one of alpha|beta|gamma|prod, got %q", appEnv)
	}
	if requiresConfigVersion(appEnv) && strings.TrimSpace(configVersion) == "" {
		return "", "", "", "", "", fmt.Errorf("CONFIG_VERSION is required when APP_ENV=%s", appEnv)
	}
	return serviceName, appEnv, configRoot, configVersion, imageVersion, nil
}

func isValidAppEnv(env string) bool {
	switch env {
	case "alpha", "beta", "gamma", "prod":
		return true
	default:
		return false
	}
}

type externalAuthProviderMode string

const (
	externalAuthProviderModeRequired      externalAuthProviderMode = "required"
	externalAuthProviderModeAnonymousOnly externalAuthProviderMode = "anonymous_only"
)

func configuredExternalAuthProviderMode() (externalAuthProviderMode, error) {
	value := strings.ToLower(strings.TrimSpace(os.Getenv("USER_AUTH_EXTERNAL_PROVIDER_MODE")))
	if value == "" {
		return externalAuthProviderModeRequired, nil
	}
	mode := externalAuthProviderMode(value)
	switch mode {
	case externalAuthProviderModeRequired, externalAuthProviderModeAnonymousOnly:
		return mode, nil
	default:
		return "", fmt.Errorf("USER_AUTH_EXTERNAL_PROVIDER_MODE must be required or anonymous_only")
	}
}

// socialAuthProviderClient 只装配真实 OAuth provider。默认和所有已部署环境必须
// 注入完整凭据；只有 local-gamma 明确声明 anonymous_only 时，才保留匿名设备
// 登录并让第三方登录以结构化 unavailable 返回，绝不伪造外部身份。
func socialAuthProviderClient(cfg config) (application.ExternalAuthProviderClient, error) {
	mode, err := configuredExternalAuthProviderMode()
	if err != nil {
		return nil, err
	}
	providerConfigs := make(map[string]userintegration.ProviderOAuthConfig, len(cfg.Integration.Social.Providers))
	for name, p := range cfg.Integration.Social.Providers {
		providerConfigs[name] = userintegration.ProviderOAuthConfig{
			AppID:                strings.TrimSpace(p.AppID),
			AppSecret:            strings.TrimSpace(p.AppSecret),
			AppPrivateKeyPEM:     strings.TrimSpace(p.AppPrivateKeyPEM),
			PlatformPublicKeyPEM: strings.TrimSpace(p.PlatformPublicKeyPEM),
			MerchantPID:          strings.TrimSpace(p.MerchantPID),
			TokenURL:             strings.TrimSpace(p.TokenURL),
			UserInfoURL:          strings.TrimSpace(p.UserInfoURL),
		}
	}
	// 商用凭据只从部署密钥系统注入；YAML 仅允许承载非敏感 endpoint。
	injectSocialOAuthEnv := func(provider string, envPrefix string) {
		current := providerConfigs[provider]
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_ID")); value != "" {
			current.AppID = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_SECRET")); value != "" {
			current.AppSecret = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_APP_PRIVATE_KEY_PEM")); value != "" {
			current.AppPrivateKeyPEM = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_PLATFORM_PUBLIC_KEY_PEM")); value != "" {
			current.PlatformPublicKeyPEM = value
		}
		if value := strings.TrimSpace(os.Getenv(envPrefix + "_MERCHANT_PID")); value != "" {
			current.MerchantPID = value
		}
		providerConfigs[provider] = current
	}
	if mode == externalAuthProviderModeRequired {
		injectSocialOAuthEnv(application.SocialProviderWechat, "WECHAT_OAUTH")
		injectSocialOAuthEnv(application.SocialProviderAlipay, "ALIPAY_OAUTH")
		injectSocialOAuthEnv(application.SocialProviderQq, "QQ_OAUTH")
	}
	httpClient := userintegration.NewHTTPExternalAuthProviderClient(providerConfigs, nil)
	if mode == externalAuthProviderModeAnonymousOnly {
		return httpClient, nil
	}
	for _, provider := range []string{
		application.SocialProviderWechat,
		application.SocialProviderAlipay,
		application.SocialProviderQq,
	} {
		if !httpClient.Supports(provider) {
			return nil, fmt.Errorf("social OAuth provider %s is not configured", provider)
		}
	}
	return httpClient, nil
}

// oneTapResolver 默认只装配真实阿里云号码认证。local-gamma 的匿名 UAT
// 显式关闭外部号码认证，调用时仍返回结构化 carrier unavailable。
func oneTapResolver(cfg config) (application.OneTapPhoneResolver, error) {
	mode, err := configuredExternalAuthProviderMode()
	if err != nil {
		return nil, err
	}
	if mode == externalAuthProviderModeAnonymousOnly {
		return application.UnavailableOneTapPhoneResolver{}, nil
	}
	if !strings.EqualFold(strings.TrimSpace(cfg.Integration.OneTap.Resolver), "aliyun") {
		return nil, fmt.Errorf("one-tap resolver must be aliyun")
	}
	accessKeyID := strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ACCESS_KEY_ID"))
	accessKeySecret := strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ACCESS_KEY_SECRET"))
	if accessKeyID == "" || accessKeySecret == "" {
		return nil, fmt.Errorf("ALIYUN_DYPNS_ACCESS_KEY_ID and ALIYUN_DYPNS_ACCESS_KEY_SECRET are required")
	}
	return userintegration.NewAliyunOneTapPhoneResolver(
		accessKeyID,
		accessKeySecret,
		strings.TrimSpace(os.Getenv("ALIYUN_DYPNS_ENDPOINT")),
	)
}

func requiresConfigVersion(env string) bool {
	switch env {
	case "gamma", "prod":
		return true
	default:
		return false
	}
}

func getenvOrDefault(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	cfg := config{}
	if strings.TrimSpace(configRoot) != "" {
		defaultFile := filepath.Join(configRoot, "configs", serviceName, "default", "config.yaml")
		envFile := filepath.Join(configRoot, "configs", serviceName, appEnv, "config.yaml")
		_ = mergeConfigFile(&cfg, defaultFile)
		_ = mergeConfigFile(&cfg, envFile)
		if configVersion != "" {
			versionFile := filepath.Join(configRoot, "quwoquan_service", "services", serviceName, "configs", "releases", configVersion+".yaml")
			_ = mergeConfigFile(&cfg, versionFile)
		}
		return cfg, nil
	}
	_ = mergeConfigFile(&cfg, "configs/default/config.yaml")
	_ = mergeConfigFile(&cfg, "configs/"+appEnv+"/config.yaml")
	return cfg, nil
}

func mergeConfigFile(cfg *config, path string) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return yaml.Unmarshal(raw, cfg)
}

func applyEnvOverrides(cfg *config) {
	if v := os.Getenv("POSTGRES_DSN"); v != "" {
		cfg.Postgres.DSN = v
	}
	if v := os.Getenv("MONGODB_URI"); v != "" {
		cfg.MongoDB.URI = v
	}
	if v := os.Getenv("REDIS_ADDR"); v != "" {
		cfg.Redis.General.Addr = v
	}
	if v := os.Getenv("REDIS_REALTIME_ADDR"); v != "" {
		cfg.Redis.Realtime.Addr = v
	}
}

func validateRuntimeCompatibility(cfg config, _, _ string) error {
	if cfg.Postgres.DSN == "" {
		return fmt.Errorf("postgres.dsn is required")
	}
	return nil
}

func buildRedisRouter(cfg config) *rtredis.Router {
	rc := cfg.Redis.General
	rt := cfg.Redis.Realtime
	if strings.TrimSpace(rt.Mode) == "" {
		rt.Mode = rc.Mode
	}
	if strings.TrimSpace(rt.Addr) == "" && len(rt.Addrs) == 0 {
		rt.Addr = rc.Addr
		rt.Addrs = append([]string(nil), rc.Addrs...)
	}
	if strings.TrimSpace(rt.Password) == "" {
		rt.Password = rc.Password
	}
	if rt.DB == 0 {
		rt.DB = rc.DB
	}
	if !rt.TLS {
		rt.TLS = rc.TLS
	}
	if rt.Pool.Size == 0 {
		rt.Pool.Size = rc.Pool.Size
	}
	if rt.Pool.MinIdle == 0 {
		rt.Pool.MinIdle = rc.Pool.MinIdle
	}
	if rt.Pool.ReadTimeoutMs == 0 {
		rt.Pool.ReadTimeoutMs = rc.Pool.ReadTimeoutMs
	}
	if rt.Pool.WriteTimeoutMs == 0 {
		rt.Pool.WriteTimeoutMs = rc.Pool.WriteTimeoutMs
	}
	if rt.Pool.DialTimeoutMs == 0 {
		rt.Pool.DialTimeoutMs = rc.Pool.DialTimeoutMs
	}
	mode := rc.Mode
	if mode == "" {
		mode = "memory"
	}
	rtMode := rt.Mode
	if rtMode == "" {
		rtMode = mode
	}
	generalScene := rtredis.SceneConfig{
		Mode:         mode,
		Addr:         rc.Addr,
		Addrs:        rc.Addrs,
		Password:     rc.Password,
		DB:           rc.DB,
		TLS:          rc.TLS,
		PoolSize:     rc.Pool.Size,
		MinIdleConns: rc.Pool.MinIdle,
	}
	realtimeScene := rtredis.SceneConfig{
		Mode:         rtMode,
		Addr:         rt.Addr,
		Addrs:        rt.Addrs,
		Password:     rt.Password,
		DB:           rt.DB,
		TLS:          rt.TLS,
		PoolSize:     rt.Pool.Size,
		MinIdleConns: rt.Pool.MinIdle,
	}
	return platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"realtime": realtimeScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}
