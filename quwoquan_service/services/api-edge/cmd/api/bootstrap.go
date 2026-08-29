// api-edge is the only public business HTTP entry. Caddy terminates TLS and
// overwrites the trusted network attribute; api-edge verifies credentials,
// authorizes the generated ContractGraph operation, consumes shared Redis
// quota, and only then proxies to the owning service.
package bootstrap

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rtobs "quwoquan_service/runtime/observability"
	"quwoquan_service/runtime/servicekit"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
	admissionapp "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	admissionmetrics "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/observability"
	admissionredis "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
	rollouthttp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/adapters/inbound/http"
	rolloutapp "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/application"
	rolloutnetworkcatalog "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/networkcatalog"
	rolloutmetrics "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/observability"
	rolloutredis "quwoquan_service/services/api-edge/internal/edge_security/rollout_assignment/infrastructure/redisstore"
	graphread "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/adapters/inbound/http"
	ownerquery "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/owner"
	registryinfra "quwoquan_service/services/api-edge/internal/graphql_read/persisted_query_execution/infrastructure/registry"

	"github.com/prometheus/client_golang/prometheus"
)

const serviceName = "api-edge"

// ownerProxyBudgetAllowance is transport-only headroom outside each generated
// owner operation budget. For POST /search this produces 2000ms at API Edge
// over Search's canonical 1500ms, while GraphQL retains its separate
// 3000ms -> 2000ms client -> 1500ms owner cascade.
const ownerProxyBudgetAllowance = 500 * time.Millisecond

// DeclaredEnvKeys 暴露声明派生的 env 覆盖键全集，供等价断言测试锁定键集不
// 随重构漂移。
func DeclaredEnvKeys() ([]string, error) {
	return servicekit.EnvOverrideKeys(
		servicekit.DefaultEnvPrefix(serviceName), &runtimeConfig{},
	)
}

// NewModule assembles api-edge's private dependencies and its HTTP contract
// surface. Binding, readiness admission and shutdown remain process lifecycle
// responsibilities of servicehost.
//
// 入站顺序是 services/api-edge/AGENTS.md 的明文契约：
//
//	credential verification -> generated operation authorization
//	-> shared admission -> owner proxy
//
// 三个声明位共同还原它：认证由骨架 auth 栈承担（operation guard 之外）、
// OperationGuard 承载受 guard 保护那一面的复合闸门、Assemble 把共享准入与
// rollout 挂到 asm.Mux。取证见 inbound_contract_order__local_contract_test.go。
//
// 不声明 CORS：api-edge 迁移前不挂载任何跨域中间件，OPTIONS 由 ContractGraph
// 裁决为 route_not_found。骨架默认即不挂载，此处刻意留空。
func NewModule() (*servicekit.Module, error) {
	return servicekit.Bootstrap(serviceName, newBootstrapSpec())
}

// newBootstrapSpec 是 api-edge 交给骨架的全部声明，也是顺序取证测试读取的
// 同一个对象：声明位一旦漂移（如把最低版本闸门挪到 WrapHandler、或补上
// CORS），测试立即变红。
func newBootstrapSpec() servicekit.BootstrapSpec[runtimeConfig] {
	// minimumBuildMiddleware 由领域装配填充。骨架的相位顺序是
	// Assemble → OperationGuard(identity)，因此 guard 工厂被调用时它已就位；
	// 缺失即 fail-closed，不退化成无闸门。
	var minimumBuildMiddleware func(http.Handler) http.Handler
	descriptors := admissionapp.AllOperationDescriptors()

	return servicekit.BootstrapSpec[runtimeConfig]{
		OperationDescriptors: descriptors,
		AuthorityScopes:      []string{"user.account.security.read"},
		// 运营台身份走 OIDC；prod 缺配置即 fail-closed。
		OperatorOIDCEnvPrefix: "OPS_OIDC",
		// 边缘同时观察原始凭据头与已解析 principal，trace 的 input/output KV
		// 必须过脱敏策略。
		ObservabilityKVFilter: rtobs.NewKVMetadataFilter(nil),
		ValidateConfig:        validateEdgeConfig,
		// 凭据中继必须在认证中间件之外：认证会把原始 Authorization 与
		// X-Device-Ticket 换成 principal 上下文，owner proxy 只能在认证与
		// operation guard 都通过之后再把它们恢复出来。
		WrapOutsideAuth: httpadapter.PreserveCredentialTransport,
		OperationGuard: func(
			identity servicekit.Identity,
		) (func(http.Handler) http.Handler, error) {
			operationAuthorization, err := rtauth.OperationAuthorizationForRuntime(
				descriptors,
				identity.AppEnv,
				os.LookupEnv,
			)
			if err != nil {
				return nil, fmt.Errorf("operation authorization boundary invalid: %w", err)
			}
			if minimumBuildMiddleware == nil {
				return nil, errors.New("minimum build middleware was not assembled")
			}
			return edgeOperationGuard(minimumBuildMiddleware, operationAuthorization), nil
		},
		Assemble: func(asm *servicekit.Assembly, config *runtimeConfig) error {
			middleware, err := assembleEdgeDomain(asm, config)
			if err != nil {
				return err
			}
			minimumBuildMiddleware = middleware
			return nil
		},
	}
}

// edgeOperationGuard 是守卫「受 operation guard 保护那一面」的复合闸门：一个
// 声明位里串起两层，最低支持版本闸门在 generated operation authorization 之外，
// 与迁移前的生效顺序逐层一致。
//
// 它挂在 OperationGuard 而不是 WrapHandler，因为骨架只用 guard 包
// assembly.Mux——放 WrapHandler 会把闸门扩到 /healthz、/readyz、/metrics、
// /graphql 与 /realtime/ws，而迁移前这五个面都不过最低版本闸门。这就是
// OperationGuard 这个声明位的设计意图，不是对它的滥用。
func edgeOperationGuard(
	minimumBuildMiddleware func(http.Handler) http.Handler,
	operationAuthorization func(http.Handler) http.Handler,
) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return rollouthttp.MinimumBuildForAuthenticatedClients(
			minimumBuildMiddleware,
			operationAuthorization(next),
		)
	}
}

// edgeBusinessSurface 复合 operation guard 之内的业务层：
// shared admission -> rollout decision -> owner proxy。
// 它是这三层顺序的唯一构造点，顺序取证测试直接穿过它。
func edgeBusinessSurface(
	admissionMiddleware func(http.Handler) http.Handler,
	rolloutMiddleware func(http.Handler) http.Handler,
	ownerProxy http.Handler,
) http.Handler {
	return admissionMiddleware(rolloutMiddleware(ownerProxy))
}

// assembleEdgeDomain 装配 api-edge 的私有依赖并注册三个入站面，返回最低支持
// 版本闸门供 OperationGuard 复合。
func assembleEdgeDomain(
	asm *servicekit.Assembly, config *runtimeConfig,
) (func(http.Handler) http.Handler, error) {
	descriptors := admissionapp.AllOperationDescriptors()
	if err := admissionapp.ValidateDescriptorOwners(descriptors); err != nil {
		return nil, err
	}

	rolloutNetworkResolver, err := rolloutnetworkcatalog.Load(
		config.Rollout.NetworkAttributeCatalog,
		config.Rollout.Policy,
	)
	if err != nil {
		return nil, fmt.Errorf("rollout network attribute catalog invalid: %w", err)
	}

	// admission 与 rollout 共用同一个 UniversalClient：prod rollout 的 stable
	// 与 gray 必须命中同一个原子准入桶，key 不含 stage/instance。
	redisClient, err := admissionredis.NewClient(config.redisConfig())
	if err != nil {
		return nil, fmt.Errorf("shared Redis client invalid: %w", err)
	}
	asm.Cleanups.Add(func(context.Context) error {
		redisClient.Close()
		return nil
	})
	store, err := admissionredis.NewWithClient(redisClient)
	if err != nil {
		return nil, fmt.Errorf("shared admission store invalid: %w", err)
	}
	admission, err := admissionapp.NewService(
		asm.Identity.AppEnv,
		store,
		config.policySet(),
		admissionmetrics.NewMetrics(nil),
	)
	if err != nil {
		return nil, fmt.Errorf("admission service invalid: %w", err)
	}
	assignmentStore, err := rolloutredis.New(redisClient)
	if err != nil {
		return nil, fmt.Errorf("rollout assignment store invalid: %w", err)
	}
	// 分配密钥的唯一来源是配置字段（键名由其 env tag 声明，见 runtimeConfig）。
	// 长度与「rollout 开启时必需」的判据仍归领域函数，因此以定值 lookup 交给它。
	allocationKey, err := rolloutapp.AllocationKey(
		config.Rollout.Enabled,
		func(string) (string, bool) {
			return config.Rollout.AllocationKey, config.Rollout.AllocationKey != ""
		},
	)
	if err != nil {
		return nil, fmt.Errorf("rollout allocation key invalid: %w", err)
	}
	rolloutEvaluator, err := rolloutapp.NewEvaluator(
		config.Rollout.Policy,
		allocationKey,
		assignmentStore,
		30*24*time.Hour,
	)
	if err != nil {
		return nil, fmt.Errorf("rollout evaluator invalid: %w", err)
	}
	minimumBuildExemptPaths, err := config.minimumBuildExemptPaths()
	if err != nil {
		return nil, fmt.Errorf("minimum build exemptions invalid: %w", err)
	}
	minimumBuildMiddleware, err := rollouthttp.MinimumBuildMiddleware(
		config.minimumBuildPolicy(),
		minimumBuildExemptPaths,
		newMinimumBuildMetrics(nil),
	)
	if err != nil {
		return nil, fmt.Errorf("minimum build middleware invalid: %w", err)
	}

	ownerRoutes, err := buildOwnerRoutes(config.Upstreams)
	if err != nil {
		return nil, err
	}
	var candidateOwnerRoutes []httpadapter.OwnerRoute
	if config.Rollout.Enabled {
		candidateOwnerRoutes, err = buildOwnerRoutes(config.CandidateUpstreams)
		if err != nil {
			return nil, fmt.Errorf("candidate owner routes invalid: %w", err)
		}
	}
	ownerProxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes:               ownerRoutes,
		CandidateRoutes:      candidateOwnerRoutes,
		BudgetAllowance:      ownerProxyBudgetAllowance,
		TrustedNetworkHeader: config.Edge.TrustedNetworkHeader,
		ContractGraphSHA256:  operationsecurity.ContractGraphSHA256,
	})
	if err != nil {
		return nil, fmt.Errorf("owner proxy invalid: %w", err)
	}
	rolloutObserver := rolloutmetrics.NewMetrics(nil)

	asm.Health.Register("admission_redis", admission.Ready)
	asm.Health.Register("rollout_assignment_redis", rolloutEvaluator.Ready)

	if err := registerGraphQLReadSurface(
		asm, config, admission, rolloutEvaluator,
		rolloutObserver, rolloutNetworkResolver, minimumBuildMiddleware,
	); err != nil {
		return nil, err
	}

	// WebSocket identity is derived only by consuming realtime-gateway's
	// one-time ticket. It still traverses api-edge, but remains outside
	// business HTTP operation admission so the edge never invents a second
	// ticket truth. Unguarded 面不过 operation guard，因而也不过最低版本闸门、
	// 共享准入与 rollout——与迁移前把它直接挂在 root mux 上逐层一致。
	realtimeOrigin, err := parseOrigin(config.Upstreams["realtime"])
	if err != nil {
		return nil, fmt.Errorf("realtime upstream invalid: %w", err)
	}
	asm.Unguarded().Handle("GET /realtime/ws", stripEdgeOnlyHeader(
		config.Edge.TrustedNetworkHeader,
		httputil.NewSingleHostReverseProxy(realtimeOrigin),
	))

	asm.Mux.Handle("/", edgeBusinessSurface(
		httpadapter.AdmissionMiddleware(
			admission,
			httpadapter.SubjectResolver{
				TrustedNetworkHeader: config.Edge.TrustedNetworkHeader,
			},
		),
		rollouthttp.Middleware(
			rolloutEvaluator,
			rolloutNetworkResolver,
			config.Edge.TrustedNetworkHeader,
			rolloutObserver,
		),
		ownerProxy,
	))
	return minimumBuildMiddleware, nil
}

// registerGraphQLReadSurface 注册持久化查询执行面。它不过 operation guard：
// 准入与 rollout 由 runtime 在 handler 内部按同一 operation contract 消费，
// 因此挂在 Unguarded 上，与迁移前独立挂在 root mux 的 /graphql 逐层一致。
func registerGraphQLReadSurface(
	asm *servicekit.Assembly,
	config *runtimeConfig,
	admission *admissionapp.Service,
	rolloutEvaluator *rolloutapp.Evaluator,
	rolloutObserver rolloutapp.Observer,
	rolloutNetworkResolver rollouthttp.NetworkAttributeResolver,
	minimumBuildMiddleware func(http.Handler) http.Handler,
) error {
	if !config.GraphQLRead.Enabled {
		return nil
	}
	trustedPublicKeys := map[string]string{}
	if err := json.Unmarshal(
		[]byte(config.GraphQLRead.TrustedPublicKeysJSON),
		&trustedPublicKeys,
	); err != nil {
		return fmt.Errorf("GraphQL trusted public keys invalid: %w", err)
	}
	signatureVerifier, err := registryinfra.NewEd25519SignatureVerifier(trustedPublicKeys)
	if err != nil {
		return fmt.Errorf("GraphQL registry signature verifier invalid: %w", err)
	}
	registryLoader, err := registryinfra.NewSignedFileLoader(signatureVerifier)
	if err != nil {
		return fmt.Errorf("GraphQL signed registry loader invalid: %w", err)
	}
	ownerExecutor, err := assembleOwnerExecutor(asm, config)
	if err != nil {
		return err
	}
	graphRuntime, err := graphread.NewRuntime(asm.Context, graphread.Options{
		Environment:     asm.Identity.AppEnv,
		Config:          config.GraphQLRead,
		RegistryLoader:  registryLoader,
		OwnerExecutor:   ownerExecutor,
		EntryValidator:  ownerquery.ValidateExecutableEntry,
		Admission:       admission,
		Rollout:         rolloutEvaluator,
		RolloutObserver: rolloutObserver,
	})
	if err != nil {
		return fmt.Errorf("GraphQL read runtime invalid: %w", err)
	}
	asm.Health.Register("graphql_signed_registry", graphRuntime.Ready)
	asm.Unguarded().Handle("/graphql", rollouthttp.MinimumBuildForAuthenticatedClients(
		minimumBuildMiddleware,
		graphread.RequestMetadataMiddleware(
			config.Edge.TrustedNetworkHeader,
			rolloutNetworkResolver,
			graphRuntime.Handler(),
		),
	))
	return nil
}

// assembleOwnerExecutor 装配 owner 侧查询执行器。三组 owner 凭据都源自同一份
// access token 配置：content owner 与 search owner 走 AuthStack.ServiceCredentials，
// search owner account 需要 service-account 形态、ServiceCredentials 表达不了，
// 因此用 AuthStack.AccessTokenConfig 自建。
func assembleOwnerExecutor(
	asm *servicekit.Assembly, config *runtimeConfig,
) (*ownerquery.QueryExecutorRouter, error) {
	stableContentOrigin, err := parseOrigin(config.Upstreams["content"])
	if err != nil {
		return nil, fmt.Errorf("GraphQL stable content owner origin invalid: %w", err)
	}
	stableSearchOrigin, err := parseOrigin(config.Upstreams["search"])
	if err != nil {
		return nil, fmt.Errorf("GraphQL stable search owner origin invalid: %w", err)
	}
	var candidateContentOrigin, candidateSearchOrigin *url.URL
	if config.Rollout.Enabled {
		candidateContentOrigin, err = parseOrigin(config.CandidateUpstreams["content"])
		if err != nil {
			return nil, fmt.Errorf("GraphQL candidate content owner origin invalid: %w", err)
		}
		candidateSearchOrigin, err = parseOrigin(config.CandidateUpstreams["search"])
		if err != nil {
			return nil, fmt.Errorf("GraphQL candidate search owner origin invalid: %w", err)
		}
	}

	ownerTimeout := time.Duration(config.GraphQLRead.OwnerTimeoutMS) * time.Millisecond
	contentOwnerCredentials, err := asm.Auth.ServiceCredentials(
		ownerquery.ContentPostOwnerReadScope(),
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL content owner credentials invalid: %w", err)
	}
	contentOwnerExecutor, err := ownerquery.NewContentPostQueryExecutor(
		stableContentOrigin,
		candidateContentOrigin,
		&http.Client{Timeout: ownerTimeout},
		operationsecurity.ContractGraphSHA256,
		contentOwnerCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL content owner executor invalid: %w", err)
	}
	searchOwnerCredentials, err := asm.Auth.ServiceCredentials(
		ownerquery.SearchOwnerReadScope(),
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL search owner credentials invalid: %w", err)
	}
	searchOwnerAccountCredentials, err := rtauth.NewHS256ServiceAccountAuthorizationProvider(
		asm.Auth.AccessTokenConfig,
		asm.Identity.ServiceName,
		[]string{ownerquery.SearchOwnerReadScope()},
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL search owner account credentials invalid: %w", err)
	}
	searchOwnerExecutor, err := ownerquery.NewSearchPageQueryExecutor(
		stableSearchOrigin,
		candidateSearchOrigin,
		&http.Client{Timeout: ownerTimeout},
		operationsecurity.ContractGraphSHA256,
		searchOwnerCredentials,
		searchOwnerAccountCredentials,
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL search owner executor invalid: %w", err)
	}
	router, err := ownerquery.NewQueryExecutorRouter(
		contentOwnerExecutor,
		searchOwnerExecutor,
	)
	if err != nil {
		return nil, fmt.Errorf("GraphQL owner executor router invalid: %w", err)
	}
	return router, nil
}

type minimumBuildMetrics struct {
	decisions *prometheus.CounterVec
}

func newMinimumBuildMetrics(registerer prometheus.Registerer) *minimumBuildMetrics {
	if registerer == nil {
		registerer = prometheus.DefaultRegisterer
	}
	metrics := &minimumBuildMetrics{
		decisions: prometheus.NewCounterVec(
			prometheus.CounterOpts{
				Name: "api_edge_minimum_build_decisions_total",
				Help: "Minimum supported client build decisions at API Edge.",
			},
			[]string{"platform", "app_build", "mode", "reason", "would_block"},
		),
	}
	registerer.MustRegister(metrics.decisions)
	return metrics
}

func (metrics *minimumBuildMetrics) ObserveMinimumBuild(
	platform, build, mode, reason string,
	wouldBlock bool,
) {
	if metrics == nil {
		return
	}
	metrics.decisions.WithLabelValues(
		rolloutapp.NormalizeMetricValue(platform, "unknown"),
		rolloutapp.NormalizeBuildMetricValue(build),
		rolloutapp.NormalizeMetricValue(mode, "unknown"),
		rolloutapp.NormalizeMetricValue(reason, "unknown"),
		strconv.FormatBool(wouldBlock),
	).Inc()
}

func buildOwnerRoutes(upstreams map[string]string) ([]httpadapter.OwnerRoute, error) {
	bindings := admissionapp.OperationOwnerBindings()
	routes := make([]httpadapter.OwnerRoute, 0, len(bindings))
	for _, binding := range bindings {
		origin, err := parseOrigin(upstreams[binding.UpstreamName])
		if err != nil {
			return nil, fmt.Errorf(
				"owner upstream %s: %w",
				binding.UpstreamName,
				err,
			)
		}
		routes = append(routes, httpadapter.OwnerRoute{
			OperationPrefix: binding.OperationPrefix,
			Upstream:        origin,
		})
	}
	return routes, nil
}

func stripEdgeOnlyHeader(header string, next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		request.Header.Del(strings.TrimSpace(header))
		next.ServeHTTP(response, request)
	})
}
