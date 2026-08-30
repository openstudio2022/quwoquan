package servicekit

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	rtpostgres "quwoquan_service/internal/platform/postgres"
)

// PostgresConfig 是可选 Postgres 场景构件的统一 YAML 段（DEC-028）。
// dsn 必填且只来自渲染配置或部署面 env 覆盖；池参数留空时采用平台层默认值，
// 它们与迁移前各服务手写的池参数一致，不引入第二套默认。
type PostgresConfig struct {
	DSN                    string `yaml:"dsn" env:"POSTGRES_DSN" required:"true"`
	MaxOpenConns           int    `yaml:"max_open_conns" env:"POSTGRES_MAX_OPEN_CONNS"`
	MaxIdleConns           int    `yaml:"max_idle_conns" env:"POSTGRES_MAX_IDLE_CONNS"`
	ConnMaxLifetimeMinutes int    `yaml:"conn_max_lifetime_minutes" env:"POSTGRES_CONN_MAX_LIFETIME_MINUTES"`
}

const (
	// postgresReadyProbeWindow 是启动期连通性探测窗口：容器编排下
	// Postgres 可能晚于本服务就绪，装配阶段按此窗口重试而不是直接失败。
	postgresReadyProbeWindow = 30 * time.Second
	postgresReadyProbeGap    = time.Second
)

// PostgresPool 是连接池句柄的本包投影，声明式装配经 Assembly.Postgres 暴露它。
type PostgresPool = rtpostgres.Pool

// Postgres 按声明建立连接池，注册 ping 健康检查与关闭清理，并在返回前完成
// 启动期连通性探测。DSN 缺失或探测窗口内始终不可达即 fail-closed。
func (assembly *Assembly) Postgres(config PostgresConfig) (PostgresPool, error) {
	serviceName := assembly.Identity.ServiceName
	if strings.TrimSpace(config.DSN) == "" {
		return nil, fmt.Errorf("%s postgres.dsn is required", serviceName)
	}
	pool, err := rtpostgres.OpenPool(assembly.Context, rtpostgres.PoolConfig{
		DSN:                    config.DSN,
		MaxOpenConns:           config.MaxOpenConns,
		MaxIdleConns:           config.MaxIdleConns,
		ConnMaxLifetimeMinutes: config.ConnMaxLifetimeMinutes,
	})
	if err != nil {
		// DSN 非法与连接失败分开报：前者重试无用，后者可能只是依赖未就绪。
		if errors.Is(err, rtpostgres.ErrInvalidDSN) {
			return nil, fmt.Errorf("%s postgres.dsn invalid: %w", serviceName, err)
		}
		return nil, fmt.Errorf("%s postgres connect failed: %w", serviceName, err)
	}
	assembly.Cleanups.Add(func(context.Context) error {
		pool.Close()
		return nil
	})
	assembly.Health.Register("postgres", pool.Ping)

	probeCtx, cancel := context.WithTimeout(assembly.Context, postgresReadyProbeWindow)
	defer cancel()
	if err := pingPostgresUntilReady(probeCtx, pool); err != nil {
		return nil, fmt.Errorf("%s postgres unavailable: %w", serviceName, err)
	}
	return pool, nil
}

func pingPostgresUntilReady(ctx context.Context, pool PostgresPool) error {
	var lastErr error
	for {
		if err := pool.Ping(ctx); err == nil {
			return nil
		} else {
			lastErr = err
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("%w (last ping error: %v)", ctx.Err(), lastErr)
		case <-time.After(postgresReadyProbeGap):
		}
	}
}
