package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"strings"

	configapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_snapshot/application/config_layer"
	"quwoquan_service/runtime/artifactidentity"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/servicehost"
	"quwoquan_service/runtime/servicekit"
)

// platformService 汇集控制面入站 adapter 与发布收敛判据。它由声明式装配填充，
// 不再持有自己的健康检查闭包：依赖就绪统一登记到骨架的 /readyz。
type platformService struct {
	repoRoot              string
	store                 controlplane.StateStore
	configLayer           *configapp.Facade
	configLayers          http.Handler
	configTopology        http.Handler
	configInstanceReports http.Handler
	configInstanceRuntime http.Handler
	humanAuthority        http.Handler
	releaseManifestDigest string
	alertIngestToken      string
	configAckInstances    []string
	configAckMaxAgeSecs   int
}

func main() {
	if _, err := artifactidentity.LoadAndValidate(
		os.Getenv("QWQ_ARTIFACT_IDENTITY_FILE"),
		os.Getenv("APP_ENV"),
	); err != nil {
		log.Fatalf("%s artifact identity invalid: %v", serviceName, err)
	}
	servicekit.RunStandalone(serviceName, func() (servicehost.Module, error) {
		return newModule()
	})
}

func stringifyDocumentValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeRuntimeNotFound(w http.ResponseWriter, r *http.Request) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
			"接口不存在",
			"route not found",
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}
