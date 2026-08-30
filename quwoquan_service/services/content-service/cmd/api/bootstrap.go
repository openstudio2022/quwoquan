package bootstrap

import (
	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/servicekit"
)

const serviceName = "content-service"

// workerRegistry 是骨架 worker 注册器的本包别名：领域装配里十余个 relay/consumer
// 启动函数按同一注册点交出 worker，生命周期由 servicehost 的 Start/Shutdown 相位
// 统一编组。
type workerRegistry = servicekit.WorkerRegistry

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集不随
// 重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

// retiredEnvKeys 是迁移后不再有读取点的注入键。它们必须 fail-closed 而不是被
// 忽略：单进程 service-core 里无前缀键会被多个模块同时读到，而「注入了但没人
// 读」会让服务带着渲染快照里的旧值静默起来。
//
// 全部键都换成了带 CONTENT 前缀的等价键（见 DeclaredEnvKeys），部署面注入点
// 同步改名；service-core 的其余模块没有任何一个仍消费这些无前缀键。
func retiredEnvKeys() []string {
	return []string{
		"MONGO_URI",
		"REPORT_DATABASE_URL",
		"REC_MODEL_SERVICE_ENABLED",
		"REC_MODEL_SERVICE_URL",
		"REC_MODEL_SERVICE_TIMEOUT_MS",
		"TAG_SERVICE_URL",
		"TAG_SERVICE_TIMEOUT_MS",
	}
}

// NewModule 声明式装配 content-service：身份、配置快照、env 覆盖、auth、观测、
// Redis、HTTP 三件套、config sync 归 servicekit，本文件只声明本服务的契约面与
// 领域装配入口（DEC-028）。
func NewModule() (*servicekit.Module, error) {
	runtime := newContentAPIRuntime()
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		OperationDescriptors: operationsecurity.ForDomain("content"),
		AuthorityScopes:      []string{accountSecurityReadScope},
		RetiredEnvKeys:       retiredEnvKeys(),
		ValidateConfig:       validateContentConfig,
		OperationGuard:       runtime.guardOperations,
		ConfigSync: servicekit.ConfigSyncOptions{
			HotStore: runtime.hotConfigStore,
		},
		Assemble: func(asm *servicekit.Assembly, cfg *config) error {
			return assembleContentDomain(asm, cfg, runtime)
		},
	})
}
