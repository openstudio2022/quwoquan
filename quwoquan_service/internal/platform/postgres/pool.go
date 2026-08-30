// Package postgres 是 Postgres 连接池的平台层封装。它存在的理由与
// internal/platform/mongodb 相同：`runtime/**` 公共层不得直连存储驱动
// （verify_service_layering），但连接池句柄必须能穿过公共层交到服务侧，
// 所以驱动包只在本包被导入，句柄以平台层别名对外。
package postgres

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Pool 是连接池句柄的平台层投影。
type Pool = *pgxpool.Pool

// ErrInvalidDSN 区分「DSN 本身不合法」与「连接建立失败」。两者的运维处置
// 相反：前者是配置错误，重试无用；后者可能只是依赖尚未就绪。调用方按它
// 决定是否进入启动期重试窗口。
var ErrInvalidDSN = errors.New("postgres: dsn invalid")

// PoolConfig 是池参数的平台层声明。零值字段采用包内默认，不引入第二套默认。
type PoolConfig struct {
	DSN                    string
	MaxOpenConns           int
	MaxIdleConns           int
	ConnMaxLifetimeMinutes int
}

const (
	defaultMaxConns          = 20
	defaultMinConns          = 2
	defaultHealthCheckPeriod = 30 * time.Second
)

// OpenPool 解析 DSN 并建立连接池。它不做连通性探测——探测窗口属于装配策略，
// 由调用方按自己的启动语义决定。
func OpenPool(ctx context.Context, cfg PoolConfig) (Pool, error) {
	dsn := strings.TrimSpace(cfg.DSN)
	if dsn == "" {
		return nil, fmt.Errorf("%w: empty", ErrInvalidDSN)
	}
	poolConfig, err := pgxpool.ParseConfig(dsn)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrInvalidDSN, err)
	}
	poolConfig.MaxConns = defaultMaxConns
	poolConfig.MinConns = defaultMinConns
	poolConfig.HealthCheckPeriod = defaultHealthCheckPeriod
	if cfg.MaxOpenConns > 0 {
		poolConfig.MaxConns = int32(cfg.MaxOpenConns)
	}
	if cfg.MaxIdleConns > 0 {
		poolConfig.MinConns = int32(cfg.MaxIdleConns)
	}
	if cfg.ConnMaxLifetimeMinutes > 0 {
		poolConfig.MaxConnLifetime = time.Duration(cfg.ConnMaxLifetimeMinutes) * time.Minute
	}

	pool, err := pgxpool.NewWithConfig(ctx, poolConfig)
	if err != nil {
		return nil, fmt.Errorf("postgres: connect: %w", err)
	}
	return pool, nil
}
