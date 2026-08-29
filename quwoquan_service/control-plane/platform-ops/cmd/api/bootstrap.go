package main

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"

	configreporthttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/adapters/inbound/http"
	configreportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	configreportmessaging "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/messaging"
	configreportpersistence "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/infrastructure/persistence"
	confighttp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/adapters/inbound/http/config_layer"
	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	configrepository "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/infrastructure/repository"
	generatedcontrolplane "quwoquan_service/generated/control_plane"
	controlplanepersistence "quwoquan_service/internal/platform/controlplane/persistence"
	"quwoquan_service/internal/platform/pgoutbox"
	"quwoquan_service/runtime/controlplane"
	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/runtime/servicekit"
)

const serviceName = "platform-ops-service"

// configAckConvergencePath 是发布编排读取的领域专属就绪子路由。它不是骨架
// 的 /readyz：后者回答「本实例依赖是否就绪」，这里回答「本次发布的全体受管
// 实例是否都已 ACK 当前配置」，两者不可互相替代。
const configAckConvergencePath = "/readyz/config-convergence"

// resolveForInstancePath 是全体服务 config sync 循环读取自身有效配置的入口。
const resolveForInstancePath = "/control-plane/platform/configs/resolve-for-instance"

// alertIngestPath 是 Alertmanager webhook 回流入口。
const alertIngestPath = "/control-plane/platform/alerts/ingest"

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集
// 不随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(servicekit.DefaultEnvPrefix(serviceName), &config{})
}

func newModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, servicekit.BootstrapSpec[config]{
		// 授权表沿用控制面 composition 表：它同时派生服务器超时，与迁移前的
		// rtauth.ContractHTTPServerTimeouts 输入完全一致。
		OperationDescriptors: generatedcontrolplane.PlatformOperationSecurityDescriptors,
		// 运营台身份走 OIDC；prod 缺配置即 fail-closed。
		OperatorOIDCEnvPrefix: "OPS_OIDC",
		// 控制面入站面只认运营台 OIDC 与机器凭据，不接受终端用户账号
		// principal，因此不装配账号安全 authority（否则控制面反向依赖
		// user-service 才能就绪）。带账号 principal 的请求由中间件拒绝。
		SkipAccountSecurityAuthority: true,
		// 本服务不签发也不校验设备票据。
		SkipDeviceTicketAuth: true,
		RetiredEnvKeys:       retiredEnvKeys(),
		ValidateConfig:       validatePlatformOpsConfig,
		Assemble:             assemblePlatformOpsDomain,
	})
}

func assemblePlatformOpsDomain(asm *servicekit.Assembly, cfg *config) error {
	ctx := asm.Context
	repoRoot := strings.TrimSpace(cfg.RepoRoot)

	store, err := controlplanepersistence.NewPostgresStore(asm.PostgresPool, "platform-ops")
	if err != nil {
		return fmt.Errorf("control plane store invalid: %w", err)
	}
	if err := store.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("control plane schema initialization failed: %w", err)
	}

	generalRedis := asm.RedisRouter.Scene("general")
	if err := generalRedis.Ping(ctx); err != nil {
		return fmt.Errorf("redis unavailable: %w", err)
	}
	messageTransport, err := runtimemessaging.NewRedisMessageTransport(generalRedis, generalRedis)
	if err != nil {
		return fmt.Errorf("message transport invalid: %w", err)
	}
	configReportPublisher, err := configreportmessaging.NewPublisher(messageTransport)
	if err != nil {
		return fmt.Errorf("ConfigInstanceReport publisher invalid: %w", err)
	}
	configReportDispatcher, err := pgoutbox.NewDispatcher(
		asm.PostgresPool, configReportPublisher, "platform_control_plane_outbox",
	)
	if err != nil {
		return fmt.Errorf("ConfigInstanceReport outbox invalid: %w", err)
	}
	asm.Workers.Add(configReportDispatcher.Run)

	configKeyCatalog, err := configapp.NewConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfig(),
	)
	if err != nil {
		return fmt.Errorf("generated config key catalog invalid: %w", err)
	}
	// IaC 收口：配置唯一真相源是版本化发布包（config-root 树或仓库配置树），
	// 平台只提供只读快照与漂移核对，不存在任何在线写路径。
	configSnapshotSource, err := configapp.NewSnapshotSource(asm.Identity.ConfigRoot, repoRoot)
	if err != nil {
		return fmt.Errorf("config snapshot source invalid: %w", err)
	}
	configLayerFacade, err := configapp.NewFacade(configSnapshotSource, configKeyCatalog)
	if err != nil {
		return fmt.Errorf("config snapshot facade invalid: %w", err)
	}
	configLayerHandler, err := confighttp.NewHandler(configLayerFacade)
	if err != nil {
		return fmt.Errorf("config snapshot HTTP adapter invalid: %w", err)
	}

	service := &platformService{
		repoRoot:              repoRoot,
		store:                 store,
		configLayer:           configLayerFacade,
		configLayers:          configLayerHandler,
		releaseManifestDigest: strings.TrimSpace(cfg.ReleaseManifestDigest),
		alertIngestToken:      strings.TrimSpace(cfg.AlertIngestToken),
		configAckInstances:    cfg.ConfigAck.RequiredInstances,
		configAckMaxAgeSecs:   cfg.configAckMaxAgeSeconds(),
	}
	if err := composePlatformHandlers(service, asm.Identity.ConfigRoot); err != nil {
		return err
	}

	// 仓库/事实树可达性是拓扑与快照只读源的前置条件，属于依赖就绪而非进程
	// 存活，因此登记在 /readyz 而不是 /healthz。
	asm.Health.Register("repo_root", func(context.Context) error {
		if _, err := os.Stat(service.repoRoot); err != nil {
			return fmt.Errorf("repo root inaccessible: %w", err)
		}
		return nil
	})

	registerPlatformOpsRoutes(asm, service)
	return nil
}

// composePlatformHandlers 装配三个入站 HTTP adapter。任一装配失败都在启动期
// 返回错误，不再由路由注册期 panic 表达。
func composePlatformHandlers(service *platformService, configRoot string) error {
	topology, err := composeConfigSnapshotTopologyHandler(service, configRoot)
	if err != nil {
		return err
	}
	runtimeInstances, err := composeConfigInstanceRuntimeHandler(service, configRoot)
	if err != nil {
		return err
	}
	reports, err := composeConfigInstanceReportHandler(service)
	if err != nil {
		return err
	}
	service.configTopology = topology
	service.configInstanceRuntime = runtimeInstances
	service.configInstanceReports = reports
	return nil
}

// registerPlatformOpsRoutes 挂接领域路由。默认全部走骨架的 generated
// operation guard（default-deny）；只有三条入站面必须留在 guard 之外，各自
// 有独立的、更窄的准入判据：
//
//   - config ACK 收敛探针不是 ContractGraph operation，发布编排在没有运营台
//     凭据的容器内探测它，因此只暴露 ready/not_ready 而不含任何拓扑细节。
//   - resolve-for-instance 是机器面 operation，未被控制面 composition 描述符
//     表收录（该表由运营台门户 metadata 派生）。把它交给 default-deny guard
//     会直接 404，掐断全体服务的 config sync 与发布 ACK。它的准入由 handler
//     自身的 service principal + env/service 绑定承担。
//   - Alertmanager webhook 只能携带静态机器 token，无法出示契约声明的
//     service principal，故由专用 token 边界 fail-closed 校验。
func registerPlatformOpsRoutes(asm *servicekit.Assembly, service *platformService) {
	routes := newServerMux(service)
	unguarded := asm.Unguarded()
	unguarded.Handle(configAckConvergencePath, routes)
	unguarded.Handle(resolveForInstancePath, routes)
	unguarded.Handle(alertIngestPath, service.requireAlertIngestToken(routes))
	asm.Mux.Handle("/", routes)
}

func composeConfigSnapshotTopologyHandler(
	service *platformService, configRoot string,
) (http.Handler, error) {
	if service == nil {
		return nil, errors.New("config snapshot topology composition requires service")
	}
	source, err := configrepository.NewTopologySource(service.repoRoot, configRoot)
	if err != nil {
		return nil, err
	}
	facade, err := configapp.NewTopologyFacade(source)
	if err != nil {
		return nil, err
	}
	return confighttp.NewTopologyHandler(facade)
}

func composeConfigInstanceRuntimeHandler(
	service *platformService, configRoot string,
) (http.Handler, error) {
	if service == nil || service.store == nil {
		return nil, errors.New("config instance runtime composition requires state store")
	}
	topologySource, err := configrepository.NewTopologySource(service.repoRoot, configRoot)
	if err != nil {
		return nil, err
	}
	topologyReader := configreportapp.RuntimeTopologyReaderFunc(func(
		ctx context.Context,
	) (configreportapp.RuntimeTopology, error) {
		current, err := topologySource.ReadRuntimeTopology(ctx)
		if err != nil {
			return configreportapp.RuntimeTopology{}, err
		}
		result := configreportapp.RuntimeTopology{
			Environments: make(map[string]configreportapp.RuntimeTopologyEnvironment, len(current.Environments)),
			Targets:      make(map[string]configreportapp.RuntimeTopologyTarget, len(current.Targets)),
		}
		for environment, value := range current.Environments {
			workloads := make([]configreportapp.RuntimeTopologyWorkload, 0, len(value.Workloads))
			for _, workload := range value.Workloads {
				workloads = append(workloads, configreportapp.RuntimeTopologyWorkload{
					ID: workload.ID, Plane: workload.Plane, DeploymentRef: workload.DeploymentRef,
				})
			}
			result.Environments[environment] = configreportapp.RuntimeTopologyEnvironment{Workloads: workloads}
		}
		for targetID, value := range current.Targets {
			result.Targets[targetID] = configreportapp.RuntimeTopologyTarget{Environment: value.Environment}
		}
		return result, nil
	})
	facade, err := configreportapp.NewRuntimeFacade(
		service.store,
		topologyReader,
		service.releaseManifestDigest,
		nil,
	)
	if err != nil {
		return nil, err
	}
	return configreporthttp.NewRuntimeHandler(facade)
}

func composeConfigInstanceReportHandler(
	service *platformService,
) (http.Handler, error) {
	if service == nil || service.store == nil || service.configLayer == nil {
		return nil, errors.New("config instance report composition requires store and ConfigSnapshot")
	}
	atomicStore, ok := service.store.(controlplane.AtomicMutationStore)
	if !ok {
		return nil, errors.New("config instance report composition requires atomic mutation store")
	}
	stateStore, err := configreportpersistence.NewStateStore(service.store, atomicStore)
	if err != nil {
		return nil, err
	}
	desiredHash := configreportapp.DesiredHashReaderFunc(func(
		ctx context.Context,
		environment string,
		serviceName string,
	) (string, error) {
		resolved, err := service.configLayer.Resolve(ctx, controlplane.ConfigResolutionScope{
			Environment: environment,
			Service:     serviceName,
		})
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(resolved.DesiredHash), nil
	})
	return configreporthttp.NewHandler(
		configreportapp.NewCommandFacade(stateStore, desiredHash, nil),
		configreportapp.NewQueryFacade(stateStore),
		service.releaseManifestDigest,
	)
}
