package bootstrap

import (
	"net/http"

	"go.mongodb.org/mongo-driver/v2/mongo"
	fencehttp "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

// registerActiveReleaseFence 是生产组合 seam；认证与 scope 由 servicekit 的 generated operation guard 统一强制执行。
func registerActiveReleaseFence(mux *http.ServeMux, db *mongo.Database, environment string) {
	fencehttp.NewActiveReleaseFenceHandler(persistence.NewMongoActiveSupplyReader(db, environment), environment).Register(mux)
}
