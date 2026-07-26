package homepage_import_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

func TestWriteImportMetricsTextfile(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "collector", "homepage_import_gamma.prom")
	finished := time.Unix(1751900000, 0).UTC()

	if err := homepageimport.WriteImportMetricsTextfile(path, "gamma", 2, 3, 1, 0, finished); err != nil {
		t.Fatalf("writeImportMetricsTextfile: %v", err)
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read metrics textfile: %v", err)
	}
	text := string(raw)
	for _, want := range []string{
		`quwoquan_homepage_import_last_success_timestamp_seconds{env="gamma"} 1751900000`,
		`quwoquan_homepage_import_objects{env="gamma",result="created"} 2`,
		`quwoquan_homepage_import_objects{env="gamma",result="updated"} 3`,
		`quwoquan_homepage_import_objects{env="gamma",result="skipped"} 1`,
		`quwoquan_homepage_import_objects{env="gamma",result="issues"} 0`,
		"# TYPE quwoquan_homepage_import_objects gauge",
	} {
		if !strings.Contains(text, want) {
			t.Fatalf("metrics textfile missing %q:\n%s", want, text)
		}
	}
	if strings.Contains(text, ".tmp") {
		t.Fatalf("tmp artifact leaked into metrics output")
	}
	if _, err := os.Stat(path + ".tmp"); !os.IsNotExist(err) {
		t.Fatalf("tmp file must be renamed away, got err=%v", err)
	}
}
