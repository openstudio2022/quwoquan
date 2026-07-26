package homepageimport

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
)

// WriteImportMetricsTextfile 以 node_exporter textfile collector 格式落导入观测指标，
// 供 quwoquan_ops/observability/monitoring/alerts/quwoquan_alerts.yaml 的 quwoquan_entity_homepage 组消费。
// 导入是离线批任务，不产长驻 /metrics；textfile 是批任务接入 Prometheus 的标准通道。
// 写入走临时文件 + rename，避免 collector 读到半截文件。
func WriteImportMetricsTextfile(
	path string,
	env string,
	created, updated, skipped, issues int,
	finishedAt time.Time,
) error {
	var b strings.Builder
	label := fmt.Sprintf("{env=%q}", env)
	b.WriteString("# HELP quwoquan_homepage_import_last_success_timestamp_seconds homepage-import 最近一次成功完成时间\n")
	b.WriteString("# TYPE quwoquan_homepage_import_last_success_timestamp_seconds gauge\n")
	b.WriteString(fmt.Sprintf("quwoquan_homepage_import_last_success_timestamp_seconds%s %d\n", label, finishedAt.Unix()))
	b.WriteString("# HELP quwoquan_homepage_import_objects homepage-import 最近一次导入对象计数（result=created|updated|skipped|issues）\n")
	b.WriteString("# TYPE quwoquan_homepage_import_objects gauge\n")
	for result, value := range map[string]int{
		"created": created,
		"updated": updated,
		"skipped": skipped,
		"issues":  issues,
	} {
		b.WriteString(fmt.Sprintf("quwoquan_homepage_import_objects{env=%q,result=%q} %d\n", env, result, value))
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	tmp := path + ".tmp"
	if err := os.WriteFile(tmp, []byte(b.String()), 0o644); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}
