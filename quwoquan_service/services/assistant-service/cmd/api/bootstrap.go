package bootstrap

import (
	"context"
	"fmt"
	"log"
	"net/http"

	"quwoquan_service/runtime/servicekit"

	httpadapter "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimewiring"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packageports "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/ports"
)

const serviceName = "assistant-service"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集不随
// 重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// retiredEnvKeys 是迁移前无服务前缀的注入键。它们与其它服务的同名键在
// 单进程 service-core 里会互相串味（同一进程内多个模块读同一个 MONGODB_URI），
// 因此彻底退役而不是新旧并存双读。
func retiredEnvKeys() []string {
	return []string{
		"MONGODB_URI",
		"MONGODB_DATABASE",
		"POSTGRES_DSN",
		"REDIS_GENERAL_MODE",
		"REDIS_GENERAL_ADDR",
		"REDIS_GENERAL_ADDRS",
		"REDIS_GENERAL_PASSWORD",
		"REDIS_GENERAL_TLS",
		"REDIS_GENERAL_DB",
		"REDIS_REC_MODE",
		"REDIS_REC_ADDR",
		"REDIS_REC_ADDRS",
		"REDIS_REC_PASSWORD",
		"REDIS_REC_TLS",
		"REDIS_REC_DB",
	}
}

// NewModule 声明式装配 assistant-service：通用启动语义归 servicekit，
// 本文件只声明本服务的契约面与领域装配入口（DEC-028）。
func NewModule() (*servicekit.Module, error) {
	migration := &officialSkillPackageMigration{}
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: httpadapter.AssistantOperationDescriptors(),
		AuthorityScopes:      []string{"user.account.security.read"},
		// assistant 不提供设备票据认证能力：不装配其 verifier，带设备票据的
		// 请求仍被 nil verifier fail-closed 拒绝。
		SkipDeviceTicketAuth: true,
		// runtime boundary：被阻断的 operation 仍要能在真实服务上跑出
		// candidate 证据，公共边界的商用状态拒绝归 api-edge。
		OperationGuard: func(servicekit.Identity) (
			func(http.Handler) http.Handler, error,
		) {
			return httpadapter.GeneratedOperationContractHandler, nil
		},
		RetiredEnvKeys:   retiredEnvKeys(),
		ValidateConfig:   validateAssistantConfig,
		RedisScenes:      resolveRedisScenes,
		PrepareMigration: migration.run,
		Assemble: func(asm *servicekit.Assembly, cfg *config) error {
			return assembleAssistantDomain(asm, cfg, migration)
		},
	})
}

// validateAssistantConfig 承接迁移前 validateRuntimeDependenciesConfig 与
// buildRedisRouter 的领域校验：出向依赖 base_url 必填、Redis scene 必须显式
// 声明真实组网。
func validateAssistantConfig(cfg *config) error {
	if err := runtimewiring.ValidateRuntimeDependenciesConfig(*cfg); err != nil {
		return err
	}
	for name, scene := range map[string]redisSceneCfg{
		"general": cfg.Redis.General,
		"rec":     cfg.Redis.Rec,
	} {
		if err := runtimewiring.ValidateRedisSceneConfig(name, scene); err != nil {
			return err
		}
	}
	return nil
}

// resolveRedisScenes 把两段声明装配成三个 codegen scene（realtime 复用
// general 的物理实例）。
func resolveRedisScenes(cfg *config) map[string]servicekit.RedisSceneConfig {
	return runtimewiring.RedisScenes(*cfg)
}

// officialSkillPackageMigration 把 PrepareMigration 相位需要的装配产物从
// Assemble 传递到迁移钩子，避免包级可变状态。
type officialSkillPackageMigration struct {
	assembled bool
	service   *packageapplication.Service
	store     packageports.ActivationStore
	assetRoot string
}

func (migration *officialSkillPackageMigration) run(ctx context.Context) error {
	if !migration.assembled {
		return fmt.Errorf("%s skill package migration is not assembled", serviceName)
	}
	// 把官方 Skill package 激活收敛到 candidate 挂载的签名 publication:
	// 空环境首次激活、candidate 更迭受控升级、已收敛零写入,使 readiness
	// 的 active-package 检查不再与环境启动死锁。
	return bootstrapOfficialSkillPackage(
		ctx,
		migration.service,
		migration.store,
		migration.assetRoot,
	)
}

// assembleAssistantDomain 是 assistant 的领域装配入口：在骨架已装配的
// Mongo/Postgres/Redis/auth/观测面之上打开仓储、编织组件、注册路由与后台
// worker。
func assembleAssistantDomain(
	asm *servicekit.Assembly,
	cfg *config,
	migration *officialSkillPackageMigration,
) error {
	runtime := newAssistantAPIRuntime(asm, cfg)
	infrastructure, err := openAssistantInfrastructure(asm, runtime)
	if err != nil {
		return err
	}
	assistant, err := wireAssistantRuntime(runtime, infrastructure)
	if err != nil {
		return err
	}
	migration.assembled = true
	migration.service = assistant.skillPackageService
	migration.store = infrastructure.dependencies.skillPackageStore
	migration.assetRoot = cfg.SkillPackage.AssetRoot

	registerAssistantRoutes(asm, runtime, infrastructure, assistant)

	// worker supervisor 自带 context 与有界关闭：装配期拉起并注册每个
	// worker 的健康检查，就绪判定因此覆盖「worker 是否真的在跑」。
	workers, err := startAssistantBackgroundWorkers(runtime, infrastructure, assistant)
	if err != nil {
		return err
	}
	asm.Cleanups.Add(func(context.Context) error { return workers.Close() })

	log.Printf("%s events storage=mongodb db=%s", serviceName, cfg.MongoDB.Database)
	log.Printf("%s consent storage=postgres", serviceName)
	return nil
}

// newAssistantAPIRuntime 把骨架装配面投影成领域装配已有的 runtime 视图，
// 使 4700 行领域编织代码无需感知装配来源。
func newAssistantAPIRuntime(asm *servicekit.Assembly, cfg *config) *assistantAPIRuntime {
	return &assistantAPIRuntime{
		appEnv:                   asm.Identity.AppEnv,
		config:                   *cfg,
		instanceID:               asm.Identity.InstanceID,
		accessTokenConfig:        asm.Auth.AccessTokenConfig,
		accessVerifier:           asm.Auth.AccessVerifier,
		accountSecurityAuthority: asm.Auth.AccountSecurityAuthority,
		ioLogger:                 asm.Observability.IOLogger,
		processLogger:            asm.Observability.ProcessLogger,
		exceptionLogger:          asm.Observability.ExceptionLogger,
	}
}

func openAssistantInfrastructure(
	asm *servicekit.Assembly,
	runtime *assistantAPIRuntime,
) (*assistantInfrastructure, error) {
	ctx := asm.Context
	redisProbeCtx, cancel := context.WithTimeout(ctx, dependencyProbeTimeout)
	defer cancel()
	if err := asm.RedisRouter.PingAll(redisProbeCtx); err != nil {
		return nil, dependencyError("redis", "connectivity", err)
	}
	messageTransport, err := requireAssistantAPIMessageTransport(
		ctx,
		runtime.appEnv,
		asm.RedisRouter,
		asm.RedisSceneModes,
	)
	if err != nil {
		return nil, dependencyError("runtime.message.transport", "preflight", err)
	}
	dependencies, err := openPersistentDependencies(ctx, asm.MongoDB, asm.PostgresPool)
	if err != nil {
		return nil, err
	}
	return &assistantInfrastructure{
		router:           asm.RedisRouter,
		messageTransport: messageTransport,
		healthChecker:    asm.Health,
		dependencies:     dependencies,
	}, nil
}
