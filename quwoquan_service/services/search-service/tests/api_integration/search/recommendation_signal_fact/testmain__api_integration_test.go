package api_integration

import (
	"context"
	"os"
	"testing"
	"time"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtredis "quwoquan_service/runtime/redis"
)

var (
	realRedisClient rtredis.Client
	redisRouter     *rtredis.Router
)

func TestMain(m *testing.M) {
	startupCtx, startupCancel := context.WithTimeout(
		context.Background(),
		2*time.Minute,
	)
	redisRuntime, err := testinfra.StartRealRedis(startupCtx)
	startupCancel()
	if err != nil {
		panic("search recommendation signal api_integration requires real Redis: " + err.Error())
	}
	if err := redisRuntime.FlushDBs(context.Background(), 0); err != nil {
		panic("flush search recommendation signal Redis: " + err.Error())
	}
	redisRouter = platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     redisRuntime.Addr,
				Password: redisRuntime.Password,
				DB:       0,
				TLS:      redisRuntime.TLS,
			},
		},
		DefaultScene: "general",
	})
	realRedisClient = redisRouter.Scene("general")

	code := m.Run()

	_ = redisRouter.Close()
	shutdownCtx, shutdownCancel := context.WithTimeout(
		context.Background(),
		30*time.Second,
	)
	_ = redisRuntime.Close(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}
