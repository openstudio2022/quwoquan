package servicekit

import (
	"context"
	"fmt"
	"strings"

	rtmongo "quwoquan_service/internal/platform/mongodb"
)

// MongoConfig 是可选 Mongo 场景构件的统一 YAML 段（DEC-028）：uri 与
// database 均为必填，env 覆盖键为 <PREFIX>_MONGO_URI / <PREFIX>_MONGO_DATABASE。
type MongoConfig struct {
	URI      string `yaml:"uri" env:"MONGO_URI" required:"true"`
	Database string `yaml:"database" env:"MONGO_DATABASE" required:"true"`
}

// MongoDatabase 是 database 句柄的本包投影，声明式装配经 Assembly.MongoDB
// 暴露它。驱动类型收在 internal/platform/mongodb，公共层不直连存储驱动。
type MongoDatabase = rtmongo.Database

type mongoConnectFunc func(ctx context.Context, cfg rtmongo.ConnectConfig) (rtmongo.Handle, error)

// defaultMongoConnect 是包级注入点：生产恒为真实驱动连接，同包白盒测试
// 以 typed double 临时替换来验证装配编排。
var defaultMongoConnect mongoConnectFunc = rtmongo.Open

// Mongo 按声明连接 MongoDB 并自动注册 ping 健康检查与断连清理，返回目标
// database 句柄。物理组网只来自渲染配置与部署面 env 覆盖，缺失即 fail-closed。
func (assembly *Assembly) Mongo(config MongoConfig) (MongoDatabase, error) {
	serviceName := assembly.Identity.ServiceName
	if strings.TrimSpace(config.URI) == "" {
		return nil, fmt.Errorf("%s mongo.uri is required", serviceName)
	}
	if strings.TrimSpace(config.Database) == "" {
		return nil, fmt.Errorf("%s mongo.database is required", serviceName)
	}

	client, err := assembly.mongoConnect(assembly.Context, rtmongo.ConnectConfig{URI: config.URI})
	if err != nil {
		return nil, fmt.Errorf("%s mongodb connect failed: %w", serviceName, err)
	}
	assembly.Cleanups.Add(func(cleanupCtx context.Context) error {
		return client.Disconnect(cleanupCtx)
	})
	assembly.Health.Register("mongodb", client.Ping)
	return client.Database(config.Database), nil
}
