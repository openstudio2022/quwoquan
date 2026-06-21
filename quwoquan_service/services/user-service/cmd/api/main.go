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

	rtauth "quwoquan_service/runtime/auth"
	rtgov "quwoquan_service/runtime/governance"
	rthealth "quwoquan_service/runtime/health"
	rthttp "quwoquan_service/runtime/http"
	rtmetrics "quwoquan_service/runtime/metrics"
	rtmongo "quwoquan_service/runtime/mongodb"
	robs "quwoquan_service/runtime/observability"
	rtotel "quwoquan_service/runtime/otel"

	rtredis "quwoquan_service/runtime/redis"
	runtimesync "quwoquan_service/runtime/sync"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
	"quwoquan_service/services/user-service/internal/adapters/mq"
	"quwoquan_service/services/user-service/internal/application"
	"quwoquan_service/services/user-service/internal/infrastructure/cache"
	userintegration "quwoquan_service/services/user-service/internal/infrastructure/integration"
	"quwoquan_service/services/user-service/internal/infrastructure/persistence"
	"quwoquan_service/services/user-service/internal/infrastructure/projection"
	"quwoquan_service/services/user-service/internal/infrastructure/searchindex"
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
		SmsOTP                     struct {
			PassThroughEnabled   bool                 `yaml:"pass_through_enabled"`
			PassThroughDebtID    string               `yaml:"pass_through_debt_id"`
			PassThroughOwner     string               `yaml:"pass_through_owner"`
			PassThroughExpiresAt string               `yaml:"pass_through_expires_at"`
			DebugRevealEnabled   bool                 `yaml:"debug_reveal_enabled"`
			SandboxAllowlist     sandboxAllowlistCfg  `yaml:"sandbox_allowlist"`
		} `yaml:"sms_otp"`
		Social struct {
			SandboxAllowlist sandboxAllowlistCfg            `yaml:"sandbox_allowlist"`
			Providers        map[string]providerOAuthCfg    `yaml:"providers"`
		} `yaml:"social"`
		OneTap struct {
			Resolver         string             `yaml:"resolver"`
			SandboxAllowlist sandboxAllowlistCfg `yaml:"sandbox_allowlist"`
			SandboxPhones    map[string]string  `yaml:"sandbox_phones"`
		} `yaml:"one_tap"`
	} `yaml:"integration"`
}

type sandboxAllowlistCfg struct {
	Enabled   bool     `yaml:"enabled"`
	Phones    []string `yaml:"phones"`
	Tokens    []string `yaml:"tokens"`
	DebtID    string   `yaml:"debt_id"`
	Owner     string   `yaml:"owner"`
	ExpiresAt string   `yaml:"expires_at"`
}

type providerOAuthCfg struct {
	AppID       string `yaml:"app_id"`
	AppSecret   string `yaml:"app_secret"`
	TokenURL    string `yaml:"token_url"`
	UserInfoURL string `yaml:"user_info_url"`
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
	blockStore := persistence.NewPgBlockStore(pgPool)
	greetingStore := persistence.NewPgGreetingStore(pgPool)
	workStore := persistence.NewPgWorkStore(pgPool)
	lifeItemStore := persistence.NewPgLifeItemStore(pgPool)
	credentialStore := persistence.NewPgCredentialBindingStore(pgPool)
	userAuthStore := persistence.NewPgUserAuthStore(pgPool)
	userDeviceStore := persistence.NewPgUserDeviceStore(pgPool)
	consentRecordStore := persistence.NewPgConsentRecordStore(pgPool)
	anonymousDeviceBindingStore := persistence.NewPgAnonymousDeviceBindingStore(pgPool)
	contactDiscoveryStore := persistence.NewPgContactDiscoveryStore(pgPool)
	inviteStore := persistence.NewPgInviteStore(pgPool)

	var followStore *persistence.MongoFollowStore
	if mongoDB != nil {
		followStore = persistence.NewMongoFollowStore(mongoDB)
		if err := followStore.EnsureIndexes(ctx); err != nil {
			log.Printf("WARN: follow_edges index creation: %v", err)
		}
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
	blockCache := cache.NewBlockCache(redisClient)
	// The domain MQ publisher stays the primary; when ES is enabled the search
	// projector is composed onto the fan-out tail (best-effort, never blocks).
	var userEventPublisher application.UserEventPublisher = mq.NewEventPublisher(redisClient)
	if searchBuilt.Projector != nil {
		userEventPublisher = searchindex.ComposePublisher(userEventPublisher, searchBuilt.Projector)
	}
	userSyncService := runtimesync.NewService(redisClient, redisRouter.Scene("realtime"))

	// 7. Services
	profileService := application.NewProfileService(
		profileStore,
		personaStore,
		settingStore,
		profileCache,
		settingCache,
		userEventPublisher,
		userSyncService,
	)
	searchService := application.NewSearchService(profileStore, personaStore, redisClient)
	followService := application.NewFollowService(
		followStore,
		profileStore,
		personaStore,
		profileCache,
		blockStore,
		userEventPublisher,
	)
	chatServiceBaseURL := getenvOrDefault("CHAT_SERVICE_BASE_URL", "")
	var conversationGateway application.ConversationGateway = application.NoopConversationGateway()
	if chatServiceBaseURL != "" {
		conversationGateway = userintegration.NewChatServiceClient(chatServiceBaseURL, nil)
	}
	greetingService := application.NewGreetingService(
		greetingStore,
		followStore,
		blockStore,
		conversationGateway,
		userEventPublisher,
	)
	blockService := application.NewBlockService(blockStore, followStore, blockCache, userEventPublisher, greetingStore)
	personaService := application.NewPersonaService(personaStore, pgPool, profileCache)
	workService := application.NewWorkService(workStore)
	lifeItemService := application.NewLifeItemService(lifeItemStore)
	settingService := application.NewSettingService(settingStore, settingCache)
	otpCodeCache := cache.NewOtpCodeCache(redisClient)
	otpChallengeStore := persistence.NewPgOtpChallengeStore(pgPool)
	externalInteractionBaseURL := getenvOrDefault("INTEGRATION_EXTERNAL_INTERACTION_BASE_URL", cfg.Integration.ExternalInteractionBaseURL)
	externalInteractionClient, err := userintegration.NewExternalInteractionClient(externalInteractionBaseURL, appEnv, nil)
	if err != nil {
		log.Fatalf("external interaction client init failed: %v", err)
	}
	passThroughConfig, err := smsOtpPassThroughConfig(cfg, isProdRuntimeEnv())
	if err != nil {
		log.Fatalf("sms otp pass-through config invalid: %v", err)
	}
	otpSandboxAllowlist, err := smsOtpSandboxAllowlist(cfg, isProdRuntimeEnv())
	if err != nil {
		log.Fatalf("sms otp sandbox allowlist invalid: %v", err)
	}
	socialProviderClient, err := socialAuthProviderClient(cfg, appEnv, isProdRuntimeEnv())
	if err != nil {
		log.Fatalf("social auth provider client init failed: %v", err)
	}
	oneTapResolverImpl, err := oneTapResolver(cfg, appEnv)
	if err != nil {
		log.Fatalf("one tap resolver init failed: %v", err)
	}
	accessTokenSecret := []byte(getenvOrDefault("AUTH_JWT_SECRET", "dev-user-service-access-secret"))
	accessSigner := rtauth.NewHS256Signer(accessTokenSecret, 30*time.Minute)
	accessVerifier := rtauth.NewHS256Verifier(accessTokenSecret)
	authService := application.NewAuthService(
		profileStore,
		personaStore,
		credentialStore,
		anonymousDeviceBindingStore,
		profileCache,
		shardDirectory,
		application.WithUserAuthRepository(userAuthStore),
		application.WithUserDeviceRepository(userDeviceStore),
		application.WithConsentRepository(consentRecordStore),
		application.WithOtpCodeStore(otpCodeCache),
		application.WithOtpChallengeStore(otpChallengeStore),
		application.WithExternalInteractionClient(externalInteractionClient),
		application.WithSmsOtpPassThroughConfig(passThroughConfig),
		application.WithSmsOtpSandboxAllowlist(otpSandboxAllowlist),
		application.WithOtpDebugReveal(smsOtpDebugRevealEnabled(cfg, isProdRuntimeEnv())),
		application.WithExternalAuthProviderClient(socialProviderClient),
		application.WithOneTapPhoneResolver(oneTapResolverImpl),
		application.WithAccessTokenSigner(accessSigner),
		application.WithDefaultNicknamePrefix(getenvOrDefault("USER_DEFAULT_NICKNAME_PREFIX", "新同学")),
	)
	subAccountService := application.NewSubAccountService(personaStore, profileStore, profileCache)
	contactDiscoveryService := application.NewContactDiscoveryService(contactDiscoveryStore)
	inviteService := application.NewInviteService(inviteStore, personaStore)

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
	handler := httpadapter.NewUserHandler(
		profileService, searchService, followService, blockService, greetingService,
		personaService, workService, lifeItemService, settingService,
		authService, subAccountService, contactDiscoveryService, inviteService,
		interestProfileService,
	).Routes()

	// 统一鉴权中间件：Bearer JWT 本地验签，验签通过后用 token principal 覆盖
	// X-Client-User-Id，杜绝裸头伪造；非法 token 清除裸身份头。仅作用于业务路由。
	authedHandler := rtauth.Middleware(accessVerifier)(handler)

	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle("/", authedHandler)

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
		Addr:              addr,
		Handler:           rateLimited,
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

// isProdRuntimeEnv 仅在 APP_ENV=prod 时为 true；非生产允许 SendOtp 返回调试码。
func isProdRuntimeEnv() bool {
	return getenvOrDefault("APP_ENV", "alpha") == "prod"
}

func smsOtpPassThroughConfig(cfg config, isProduction bool) (application.SmsOtpPassThroughConfig, error) {
	enabled := cfg.Integration.SmsOTP.PassThroughEnabled
	if raw := strings.TrimSpace(os.Getenv("SMS_OTP_PASS_THROUGH_ENABLED")); raw != "" {
		enabled = strings.EqualFold(raw, "true") || raw == "1"
	}
	mode := application.SmsOtpPassThroughDisabled
	if enabled {
		mode = application.SmsOtpPassThroughEnabled
	}
	expiresRaw := strings.TrimSpace(getenvOrDefault("SMS_OTP_PASS_THROUGH_EXPIRES_AT", cfg.Integration.SmsOTP.PassThroughExpiresAt))
	var expiresAt time.Time
	if expiresRaw != "" {
		parsed, err := time.Parse("2006-01-02", expiresRaw)
		if err != nil {
			return application.SmsOtpPassThroughConfig{}, err
		}
		expiresAt = parsed.UTC()
	}
	config := application.SmsOtpPassThroughConfig{
		Mode:      mode,
		DebtID:    getenvOrDefault("SMS_OTP_PASS_THROUGH_DEBT_ID", cfg.Integration.SmsOTP.PassThroughDebtID),
		Owner:     getenvOrDefault("SMS_OTP_PASS_THROUGH_OWNER", cfg.Integration.SmsOTP.PassThroughOwner),
		ExpiresAt: expiresAt,
	}
	return config, config.Validate(isProduction)
}

// buildSandboxAllowlist 从配置构造受控放通白名单（gamma 用）；生产强制为空（由 Validate 拦截）。
func buildSandboxAllowlist(raw sandboxAllowlistCfg) (application.SandboxAllowlist, error) {
	list := application.SandboxAllowlist{
		Enabled: raw.Enabled,
		Phones:  raw.Phones,
		Tokens:  raw.Tokens,
		DebtID:  strings.TrimSpace(raw.DebtID),
		Owner:   strings.TrimSpace(raw.Owner),
	}
	if expires := strings.TrimSpace(raw.ExpiresAt); expires != "" {
		parsed, err := time.Parse("2006-01-02", expires)
		if err != nil {
			return application.SandboxAllowlist{}, err
		}
		list.ExpiresAt = parsed.UTC()
	}
	return list, nil
}

func smsOtpSandboxAllowlist(cfg config, isProduction bool) (application.SandboxAllowlist, error) {
	list, err := buildSandboxAllowlist(cfg.Integration.SmsOTP.SandboxAllowlist)
	if err != nil {
		return application.SandboxAllowlist{}, err
	}
	return list, list.Validate(isProduction)
}

func socialSandboxAllowlist(cfg config, isProduction bool) (application.SandboxAllowlist, error) {
	list, err := buildSandboxAllowlist(cfg.Integration.Social.SandboxAllowlist)
	if err != nil {
		return application.SandboxAllowlist{}, err
	}
	return list, list.Validate(isProduction)
}

// socialAuthProviderClient 按环境选择社交票据置换实现：
//   - alpha/beta：mock（离线确定性身份，发布安全）；
//   - gamma：sandbox 包装（命中 allowlist 返回沙箱身份，其余委托真实 HTTP）；
//   - prod：真实 HTTP（微信标准流程；支付宝/QQ 待配置 app 凭证）。
func socialAuthProviderClient(cfg config, appEnv string, isProduction bool) (application.ExternalAuthProviderClient, error) {
	providerConfigs := make(map[string]userintegration.ProviderOAuthConfig, len(cfg.Integration.Social.Providers))
	for name, p := range cfg.Integration.Social.Providers {
		providerConfigs[name] = userintegration.ProviderOAuthConfig{
			AppID:       strings.TrimSpace(p.AppID),
			AppSecret:   strings.TrimSpace(p.AppSecret),
			TokenURL:    strings.TrimSpace(p.TokenURL),
			UserInfoURL: strings.TrimSpace(p.UserInfoURL),
		}
	}
	httpClient := userintegration.NewHTTPExternalAuthProviderClient(providerConfigs, nil)
	switch appEnv {
	case "alpha", "beta":
		return userintegration.NewMockExternalAuthProviderClient(), nil
	case "gamma":
		allow, err := socialSandboxAllowlist(cfg, isProduction)
		if err != nil {
			return nil, err
		}
		return userintegration.NewSandboxExternalAuthProviderClient(allow, httpClient), nil
	default:
		return httpClient, nil
	}
}

// oneTapResolver 按环境注入一键置换：alpha/beta 用 dev 解码；gamma 用沙箱静态号段；prod 待真实运营商接入前返回不可用。
func oneTapResolver(cfg config, appEnv string) (application.OneTapPhoneResolver, error) {
	switch appEnv {
	case "alpha", "beta":
		return application.TokenEncodedOneTapPhoneResolver{}, nil
	case "gamma":
		phones := map[string]string{}
		for token, phone := range cfg.Integration.OneTap.SandboxPhones {
			phones[strings.TrimSpace(token)] = strings.TrimSpace(phone)
		}
		if len(phones) == 0 {
			return application.UnavailableOneTapPhoneResolver{}, nil
		}
		return application.StaticOneTapPhoneResolver(phones), nil
	default:
		// prod：真实运营商 resolver 待接入；在此之前不暴露 dev 解码后门。
		return application.UnavailableOneTapPhoneResolver{}, nil
	}
}

func smsOtpDebugRevealEnabled(cfg config, isProduction bool) bool {
	if isProduction {
		return false
	}
	enabled := cfg.Integration.SmsOTP.DebugRevealEnabled
	if raw := strings.TrimSpace(os.Getenv("SMS_OTP_DEBUG_REVEAL_ENABLED")); raw != "" {
		enabled = strings.EqualFold(raw, "true") || raw == "1"
	}
	return enabled
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
			versionFile := filepath.Join(configRoot, "releases", "config", serviceName, configVersion+".yaml")
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
	return rtredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general":  generalScene,
			"realtime": realtimeScene,
			"rec":      generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
}
