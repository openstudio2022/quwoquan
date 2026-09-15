package servicekit

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtmongo "quwoquan_service/internal/platform/mongodb"
)

// MongoConfig 是可选 Mongo 场景构件的统一 YAML 段（DEC-028）：uri 与
// database 均为必填，env 覆盖键为 <PREFIX>_MONGO_URI / <PREFIX>_MONGO_DATABASE。
type MongoConfig struct {
	URI      string `yaml:"uri" env:"MONGO_URI"`
	Database string `yaml:"database" env:"MONGO_DATABASE"`
}

// MongoDatabase 是 database 句柄的本包投影，声明式装配经 Assembly.MongoDB
// 暴露它。驱动类型收在 internal/platform/mongodb，公共层不直连存储驱动。
type MongoDatabase = rtmongo.Database

type MongoConnectConfig = rtmongo.ConnectConfig
type MongoHandle = rtmongo.Handle
type mongoConnectFunc func(ctx context.Context, cfg MongoConnectConfig) (MongoHandle, error)

// MongoConstructionError 标识 Mongo 在模块构造期的确定性失败；调用方可用
// errors.As 区分配置、连接与 database handle 失败，同时保留底层 cause。
type MongoConstructionError struct {
	Service string
	Stage   string
	Cause   error
}

func (err *MongoConstructionError) Error() string {
	return fmt.Sprintf("%s mongodb %s failed: %v", err.Service, err.Stage, err.Cause)
}

func (err *MongoConstructionError) Unwrap() error { return err.Cause }

// defaultMongoConnect 是包级注入点：生产恒为真实驱动连接，同包白盒测试
// 以 typed double 临时替换来验证装配编排。
var defaultMongoConnect mongoConnectFunc = rtmongo.Open

// Mongo 按声明连接 MongoDB 并自动注册默认预算的 ping 健康检查与断连清理，
// 返回目标 database 句柄。物理组网只来自渲染配置与部署面 env 覆盖，缺失即
// fail-closed。
func (assembly *Assembly) Mongo(config MongoConfig) (MongoDatabase, error) {
	return assembly.mongo(config, 0, mongoHealthCheckName)
}

// MongoNamed 装配第二个（非本服务权威）Mongo 库句柄，健康检查以调用方给定的
// 名字登记。health registry 拒绝重复名，因此同一服务内的第二条 Mongo 连接
// （如只读的跨服务 fence 库）不能再占用默认的 "mongodb" 检查名。
func (assembly *Assembly) MongoNamed(healthCheckName string, config MongoConfig) (MongoDatabase, error) {
	name := strings.TrimSpace(healthCheckName)
	if name == "" || name == mongoHealthCheckName {
		return nil, fmt.Errorf("%s mongo health check name must be a distinct non-empty name", assembly.Identity.ServiceName)
	}
	return assembly.mongo(config, 0, name)
}

// MongoWithReadinessTimeout 与 Mongo 使用同一装配路径，但允许调用方把 mongodb
// ping 的健康检查预算与驱动自身的 bounded selection 窗口对齐。非正预算沿用
// Mongo 的默认检查预算，与 health.Register 的既有 API 语义一致。
func (assembly *Assembly) MongoWithReadinessTimeout(
	config MongoConfig,
	readinessTimeout time.Duration,
) (MongoDatabase, error) {
	return assembly.mongo(config, readinessTimeout, mongoHealthCheckName)
}

const mongoHealthCheckName = "mongodb"

func (assembly *Assembly) mongo(
	config MongoConfig,
	readinessTimeout time.Duration,
	healthCheckName string,
) (MongoDatabase, error) {
	serviceName := assembly.Identity.ServiceName
	if strings.TrimSpace(config.URI) == "" {
		return nil, &MongoConstructionError{Service: serviceName, Stage: "config", Cause: fmt.Errorf("mongo.uri is required")}
	}
	if strings.TrimSpace(config.Database) == "" {
		return nil, &MongoConstructionError{Service: serviceName, Stage: "config", Cause: fmt.Errorf("mongo.database is required")}
	}

	client, err := assembly.mongoConnect(assembly.Context, rtmongo.ConnectConfig{URI: config.URI})
	if err != nil {
		return nil, &MongoConstructionError{Service: serviceName, Stage: "connect", Cause: err}
	}
	assembly.Cleanups.Add(func(cleanupCtx context.Context) error {
		return client.Disconnect(cleanupCtx)
	})
	if readinessTimeout > 0 {
		assembly.Health.RegisterWithTimeout(healthCheckName, readinessTimeout, client.Ping)
	} else {
		assembly.Health.Register(healthCheckName, client.Ping)
	}
	database := client.Database(config.Database)
	if database == nil {
		return nil, &MongoConstructionError{
			Service: serviceName,
			Stage:   "database",
			Cause:   fmt.Errorf("connector returned nil database handle"),
		}
	}
	return database, nil
}
