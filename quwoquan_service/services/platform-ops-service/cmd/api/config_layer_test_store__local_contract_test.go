package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	confighttp "quwoquan_service/services/platform-ops-service/internal/adapters/http/config_layer"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
)

// newTestConfigLayerComponents 构造 IaC 只读快照 facade/handler：
// 数据源是临时目录内的最小发布包配置树（仓库模式）。
func newTestConfigLayerComponents(t *testing.T) (*configapp.Facade, *confighttp.Handler) {
	t.Helper()
	root := t.TempDir()
	base := filepath.Join(root, "quwoquan_service", "services", "content-service", "configs")
	for path, content := range map[string]string{
		filepath.Join(base, "default", "config.yaml"): "config:\n  version: \"1.0.0\"\n",
		filepath.Join(base, "gamma", "config.yaml"):   "sys.content.mongo.max_pool_size: 130\n",
	} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatalf("mkdir: %v", err)
		}
		if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
			t.Fatalf("write: %v", err)
		}
	}
	catalog, err := configapp.NewConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfigSchema(),
	)
	if err != nil {
		t.Fatalf("build generated config catalog: %v", err)
	}
	source, err := configapp.NewSnapshotSource("", root)
	if err != nil {
		t.Fatalf("build snapshot source: %v", err)
	}
	facade, err := configapp.NewFacade(source, catalog)
	if err != nil {
		t.Fatalf("build config facade: %v", err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatalf("build config handler: %v", err)
	}
	return facade, handler
}

func TestConfigLayerTestComponentsExposeGeneratedCatalog(t *testing.T) {
	facade, handler := newTestConfigLayerComponents(t)
	if handler == nil {
		t.Fatal("expected typed config snapshot HTTP handler")
	}
	keys := facade.ListConfigKeys(context.Background())
	if len(keys) == 0 {
		t.Fatal("expected generated config key catalog")
	}
	for _, key := range keys {
		if key.UIEditable {
			t.Fatalf("IaC catalog must be read-only, key %q is editable", key.Key)
		}
	}
	domains, err := facade.ListDomains(context.Background())
	if err != nil {
		t.Fatalf("list config domains: %v", err)
	}
	if len(domains.Items) != 3 {
		t.Fatalf("expected cloud-service/app/data domains, got %+v", domains.Items)
	}
}
