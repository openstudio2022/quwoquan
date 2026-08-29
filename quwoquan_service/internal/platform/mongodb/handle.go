package mongodb

import (
	"context"

	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/readpref"
)

// Database 是驱动 database 句柄的平台层投影。装配层与领域 adapter 经它取得
// 句柄，驱动包本身只被本平台包导入——`runtime/**` 公共层不得直连存储驱动
// （verify_service_layering），而句柄类型必须能穿过公共层交到服务侧。
type Database = *mongo.Database

// Handle 是连接生命周期的平台层投影：ping 与断连不暴露驱动的 read
// preference 类型，公共层因此无需导入驱动即可注册健康检查与清理。
type Handle interface {
	Ping(ctx context.Context) error
	Disconnect(ctx context.Context) error
	Database(name string) Database
}

type driverHandle struct {
	client *mongo.Client
}

func (handle driverHandle) Ping(ctx context.Context) error {
	return handle.client.Ping(ctx, readpref.Primary())
}

func (handle driverHandle) Disconnect(ctx context.Context) error {
	return handle.client.Disconnect(ctx)
}

func (handle driverHandle) Database(name string) Database {
	return handle.client.Database(name)
}

// Open 建立连接并返回平台层句柄。它与 Connect 共用同一条连接与预检路径，
// 只是把驱动类型收在包内。
func Open(ctx context.Context, cfg ConnectConfig) (Handle, error) {
	client, err := Connect(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return driverHandle{client: client}, nil
}
