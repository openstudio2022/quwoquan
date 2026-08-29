package servicekit

import (
	"context"
	"fmt"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeconfig "quwoquan_service/runtime/config"
)

// AuthStackSpec 声明一个服务模块的 auth 栈输入。OperationDescriptors 由服务
// bootstrap 调用 operationsecurity.ForDomain(...) 构造后以值对象传入，
// servicekit 不 import generated/**。
type AuthStackSpec struct {
	OperationDescriptors []rtauth.OperationSecurityDescriptor
	// AccountSecurityAuthority 描述对 user-service 账号安全 authority 的
	// HTTP 依赖；resource-service 组合必填。
	AccountSecurityAuthority AccountSecurityAuthoritySpec
	// SkipAccountSecurityAuthority 声明本服务的入站面不接受终端用户账号
	// principal（控制面服务只认运营台 OIDC 与机器凭据），因此不装配账号安全
	// authority 客户端，也不把它的可达性并入本服务就绪。此时中间件装配
	// deniedAccountSecurityAuthority：任何需要账号安全裁决的 principal 一律
	// 被拒，而不是把「无依赖」变成放行。声明该能力却同时给出 base_url 或
	// scopes 即 fail-closed——两者是矛盾声明。
	SkipAccountSecurityAuthority bool
	// SkipDeviceTicketAuth 声明本服务不提供设备票据认证能力：不装配
	// device ticket verifier，也不要求其运行时配置在场。中间件对带设备
	// 票据的请求仍然 fail-closed 拒绝（nil verifier 即拒），不是放行。
	SkipDeviceTicketAuth bool
	// OperatorOIDCEnvPrefix 声明本服务承载运营台身份：非空时按该前缀从
	// 环境加载 OIDC verifier（issuer/audience/JWKS）。按
	// rtauth.OperatorOIDCRequiredForEnvironment 判定的环境里缺配置即
	// fail-closed，不允许无运营身份启动。
	OperatorOIDCEnvPrefix string
	// SelfHostedAccountSecurityAuthority 声明本服务**就是**账号安全 authority
	// 的提供方（user-service）。它与 SkipAccountSecurityAuthority 语义相反：
	// 后者是「不接受终端用户账号 principal」，此处是「接受，但裁决在本进程内
	// 完成」。装配 HTTP 客户端指向自己会同时制造自调用与就绪自依赖，因此不
	// 装配客户端、不登记远端就绪检查。
	//
	// 裁决不在认证中间件里做：认证中间件在 operation guard 之外，此刻
	// operation 上下文尚未写入，无法表达「已确认 closed 的账号重放某条
	// canonical 幂等终态命令仍返回成功」这类 operation 级豁免。因此自托管
	// 服务必须由领域装配经 Assembly.Auth.ProvideInProcessAccountSecurityGate
	// 交出进程内裁决中间件，由骨架挂在 operation guard **内侧**。缺提供即
	// fail-closed：中间件侧的 authority 面在自托管形态下是 nil，而 nil 意味着
	// 认证层跳过账号安全检查——若领域 gate 也缺席，账号安全就静默失效了。
	//
	// 它与 SkipAccountSecurityAuthority、authority base_url、scopes 均互斥。
	SelfHostedAccountSecurityAuthority bool
}

// AccountSecurityAuthoritySpec 是账号安全 authority 客户端的装配声明。
type AccountSecurityAuthoritySpec struct {
	BaseURL   string
	TimeoutMs int
	// Scopes 是该服务向 authority 声明的最小服务间授权范围。
	Scopes []string
}

// AuthStack 汇集 token 校验、operation guard 与契约派生的服务器超时。
type AuthStack struct {
	AccessTokenConfig    rtauth.TokenConfig
	AccessVerifier       *rtauth.Verifier
	DeviceTicketVerifier *rtauth.Verifier
	OperatorOIDCVerifier *rtauth.OIDCVerifier
	// AccountSecurityAuthority 是远端账号安全 authority 客户端；声明
	// SkipAccountSecurityAuthority 的服务此处为 nil，就绪面也不登记它。
	AccountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority
	Timeouts                 rtauth.HTTPServerTimeouts

	// accountSecurityGate 是认证中间件消费的账号安全裁决面：装配了客户端时
	// 就是它，声明缺席时是 deniedAccountSecurityAuthority，自托管时是 nil
	// （裁决改由 operation guard 内侧的领域 gate 承担）。
	accountSecurityGate rtauth.AccountSecurityAuthority
	// selfHostedAuthority 记录本服务是 authority 提供方，领域 gate 待提供。
	selfHostedAuthority bool
	// inProcessAccountSecurityGate 是自托管服务的进程内裁决中间件，由骨架挂在
	// operation guard 内侧。
	inProcessAccountSecurityGate func(http.Handler) http.Handler
	serviceName                  string
	descriptors                  []rtauth.OperationSecurityDescriptor
}

// ProvideInProcessAccountSecurityGate 交出自托管服务的进程内账号安全裁决
// 中间件。骨架把它挂在 operation guard 内侧，因此 gate 能读到 operation
// 上下文并表达 operation 级豁免。仅声明了 SelfHostedAccountSecurityAuthority
// 的服务可调用，且只能提供一次：账号安全是单一裁决点，允许覆盖等于给同一
// 决定留两条轨。挂载位置由骨架决定而非服务侧手工组装——位置错了（挂到
// guard 外侧）就拿不到 operation 上下文，而那种错误在运行期只表现为某条
// 幂等重放语义悄悄失效。
func (stack *AuthStack) ProvideInProcessAccountSecurityGate(
	gate func(http.Handler) http.Handler,
) error {
	if !stack.selfHostedAuthority {
		return fmt.Errorf(
			"%s did not declare SelfHostedAccountSecurityAuthority", stack.serviceName,
		)
	}
	if gate == nil {
		return fmt.Errorf("%s in-process account security gate is nil", stack.serviceName)
	}
	if stack.inProcessAccountSecurityGate != nil {
		return fmt.Errorf(
			"%s in-process account security gate is already provided", stack.serviceName,
		)
	}
	stack.inProcessAccountSecurityGate = gate
	return nil
}

// requireAccountSecurityDecisionPoint 在领域装配之后核对自托管服务确实交出了
// 裁决 gate。自托管形态下认证中间件的 authority 面是 nil，而 nil 使认证层
// 跳过账号安全检查；若领域 gate 也缺席，被封禁与已注销账号将畅通无阻，且这
// 种失效没有任何运行期信号。
func (stack *AuthStack) requireAccountSecurityDecisionPoint() error {
	if !stack.selfHostedAuthority {
		return nil
	}
	if stack.inProcessAccountSecurityGate == nil {
		return fmt.Errorf(
			"%s declared SelfHostedAccountSecurityAuthority but provided no in-process gate",
			stack.serviceName,
		)
	}
	return nil
}

// deniedAccountSecurityAuthority 是「本服务不接受终端用户账号 principal」的
// 生产策略实现。它不是测试替身：声明该形态的服务把这类 principal 视为不可裁决，
// 中间件按 unavailable 拒绝请求，而不是绕过账号状态检查放行。
type deniedAccountSecurityAuthority struct{}

func (deniedAccountSecurityAuthority) ReadAccountSecurity(
	context.Context, string,
) (rtauth.AccountSecuritySnapshot, error) {
	return rtauth.AccountSecuritySnapshot{}, rtauth.ErrAccountSecurityUnavailable
}

// ServiceCredentials 为指定 scopes 派生一份服务间授权凭据。承载多组 scope
// （如账号处置写、申诉受理）的服务在领域装配里按需取用，凭据来源仍是同一
// access token 配置，不引入第二套签发真相源。
func (stack *AuthStack) ServiceCredentials(
	scopes ...string,
) (rtauth.ServiceAuthorizationProvider, error) {
	provider, err := rtauth.NewHS256ServiceAuthorizationProvider(
		stack.AccessTokenConfig, stack.serviceName, scopes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"%s service credential init failed for scopes %v: %w", stack.serviceName, scopes, err,
		)
	}
	return provider, nil
}

// DelegatedPersonaCredentials 为服务间只读调用派生一份带真实 persona actor 的
// 委派凭据。它与 ServiceCredentials 同源同签发面，区别只在 actor 链：委派凭据
// 保留发起调用的终端用户身份，被调方因此能施加与直连同一套数据可见性。
func (stack *AuthStack) DelegatedPersonaCredentials(
	scopes ...string,
) (rtauth.DelegatedPersonaAuthorizationProvider, error) {
	provider, err := rtauth.NewHS256DelegatedPersonaAuthorizationProvider(
		stack.AccessTokenConfig, stack.serviceName, scopes,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"%s delegated persona credential init failed for scopes %v: %w",
			stack.serviceName, scopes, err,
		)
	}
	return provider, nil
}

// NewAuthStack 从运行时配置装配 auth 栈。任何一段配置缺失或非法都返回错误，
// 不允许无鉴权启动。
func NewAuthStack(identity Identity, spec AuthStackSpec) (*AuthStack, error) {
	if len(spec.OperationDescriptors) == 0 {
		return nil, fmt.Errorf(
			"%s auth stack requires generated operation descriptors",
			identity.ServiceName,
		)
	}

	accessTokenConfig, err := rtauth.LoadAccessTokenConfig(runtimeconfig.EnvRuntimeConfigProvider{})
	if err != nil {
		return nil, fmt.Errorf("%s access token config invalid: %w", identity.ServiceName, err)
	}
	accessVerifier, err := rtauth.NewHS256Verifier(accessTokenConfig)
	if err != nil {
		return nil, fmt.Errorf("%s access token verifier invalid: %w", identity.ServiceName, err)
	}
	var deviceTicketVerifier *rtauth.Verifier
	if !spec.SkipDeviceTicketAuth {
		deviceTicketConfig, err := rtauth.LoadDeviceTicketConfig(runtimeconfig.EnvRuntimeConfigProvider{})
		if err != nil {
			return nil, fmt.Errorf("%s device ticket config invalid: %w", identity.ServiceName, err)
		}
		deviceTicketVerifier, err = rtauth.NewHS256Verifier(deviceTicketConfig)
		if err != nil {
			return nil, fmt.Errorf("%s device ticket verifier invalid: %w", identity.ServiceName, err)
		}
	}

	var operatorOIDCVerifier *rtauth.OIDCVerifier
	if prefix := strings.TrimSpace(spec.OperatorOIDCEnvPrefix); prefix != "" {
		operatorOIDCVerifier, err = rtauth.NewOIDCVerifierFromEnv(prefix)
		if err != nil {
			return nil, fmt.Errorf(
				"%s operator OIDC verifier invalid: %w", identity.ServiceName, err,
			)
		}
		if operatorOIDCVerifier == nil &&
			rtauth.OperatorOIDCRequiredForEnvironment(identity.AppEnv) {
			return nil, fmt.Errorf(
				"%s operator OIDC issuer/audience/JWKS configuration is required in %s",
				identity.ServiceName, identity.AppEnv,
			)
		}
	}

	var authority *rtauth.HTTPAccountSecurityAuthority
	var accountSecurityGate rtauth.AccountSecurityAuthority = deniedAccountSecurityAuthority{}
	if spec.SkipAccountSecurityAuthority && spec.SelfHostedAccountSecurityAuthority {
		return nil, fmt.Errorf(
			"%s declares both SkipAccountSecurityAuthority and SelfHostedAccountSecurityAuthority",
			identity.ServiceName,
		)
	}
	switch {
	case spec.SkipAccountSecurityAuthority:
		if strings.TrimSpace(spec.AccountSecurityAuthority.BaseURL) != "" ||
			len(spec.AccountSecurityAuthority.Scopes) > 0 {
			return nil, fmt.Errorf(
				"%s declares SkipAccountSecurityAuthority together with an authority base URL or scopes",
				identity.ServiceName,
			)
		}
	case spec.SelfHostedAccountSecurityAuthority:
		if strings.TrimSpace(spec.AccountSecurityAuthority.BaseURL) != "" ||
			len(spec.AccountSecurityAuthority.Scopes) > 0 {
			return nil, fmt.Errorf(
				"%s hosts the account security authority itself; an authority base URL or scopes "+
					"would point it at its own inbound face",
				identity.ServiceName,
			)
		}
		// 认证层不做裁决：裁决点是 operation guard 内侧的领域 gate，
		// 由 requireAccountSecurityDecisionPoint 保证它在场。
		accountSecurityGate = nil
	default:
		credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
			accessTokenConfig,
			identity.ServiceName,
			spec.AccountSecurityAuthority.Scopes,
		)
		if err != nil {
			return nil, fmt.Errorf(
				"%s account security authority credential init failed: %w",
				identity.ServiceName, err,
			)
		}
		authorityTimeout := time.Duration(spec.AccountSecurityAuthority.TimeoutMs) * time.Millisecond
		authority, err = rtauth.NewHTTPAccountSecurityAuthority(
			rtauth.HTTPAccountSecurityAuthorityConfig{
				BaseURL:     spec.AccountSecurityAuthority.BaseURL,
				HTTPClient:  &http.Client{Timeout: authorityTimeout},
				Credentials: credentials,
				Timeout:     authorityTimeout,
			},
		)
		if err != nil {
			return nil, fmt.Errorf(
				"%s account security authority config invalid: %w",
				identity.ServiceName, err,
			)
		}
		accountSecurityGate = authority
	}

	return &AuthStack{
		AccessTokenConfig:        accessTokenConfig,
		AccessVerifier:           accessVerifier,
		DeviceTicketVerifier:     deviceTicketVerifier,
		OperatorOIDCVerifier:     operatorOIDCVerifier,
		AccountSecurityAuthority: authority,
		Timeouts:                 rtauth.ContractHTTPServerTimeouts(spec.OperationDescriptors),
		accountSecurityGate:      accountSecurityGate,
		selfHostedAuthority:      spec.SelfHostedAccountSecurityAuthority,
		serviceName:              identity.ServiceName,
		descriptors:              spec.OperationDescriptors,
	}, nil
}

// GuardOperations 用 generated descriptor 对 handler 施加 operation 级授权门。
func (stack *AuthStack) GuardOperations(handler http.Handler) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(stack.descriptors)(handler)
}

// WrapHTTPHandler 施加统一请求认证中间件（access JWT、device ticket、
// 账号安全 authority）。
func (stack *AuthStack) WrapHTTPHandler(handler http.Handler) http.Handler {
	return rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      stack.AccessVerifier,
		DeviceTicketVerifier:     stack.DeviceTicketVerifier,
		OperatorOIDCVerifier:     stack.OperatorOIDCVerifier,
		AccountSecurityAuthority: stack.accountSecurityGate,
	})(handler)
}
