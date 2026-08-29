package bootstrap

import (
	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	runtimemessaging "quwoquan_service/runtime/messaging"
	robs "quwoquan_service/runtime/observability"
	rtredis "quwoquan_service/runtime/redis"
)

// assistantAPIRuntime 是骨架装配面在领域编织代码里的只读视图：身份、生效
// 配置、鉴权构件与日志器。它不拥有任何资源，生命周期归 servicekit。
type assistantAPIRuntime struct {
	appEnv                   string
	config                   config
	instanceID               string
	accessTokenConfig        rtauth.TokenConfig
	accessVerifier           *rtauth.Verifier
	accountSecurityAuthority *rtauth.HTTPAccountSecurityAuthority
	ioLogger                 *robs.IOAccessLogger
	processLogger            *robs.ProcessTraceLogger
	exceptionLogger          *robs.ExceptionLogger
}

// assistantInfrastructure 汇集领域装配需要的基础设施句柄。Redis 路由、
// Mongo/Postgres 连接与健康检查器都由骨架装配并负责释放。
type assistantInfrastructure struct {
	router           *rtredis.Router
	messageTransport *runtimemessaging.RedisMessageTransport
	healthChecker    *rthealth.Checker
	dependencies     *persistentDependencies
}
