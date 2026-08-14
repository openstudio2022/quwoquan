// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md#req-003
// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/analytics-metric-dictionary/spec.md#gwt-001
//
// raw 索引数值 mapping 合约：golden_metric_catalog 中 percentile_p95 /
// sum_ratio 引用的 raw value 字段必须出现在 raw 索引显式 long mapping
// 清单中；缺席会落入 keyword 动态模板，使 ES 数值聚合 400、L1-L4 快照
// 派生失败（alpha 实测回归：jankyFrames/sampledFrames）。
package local_contract

import (
	"testing"

	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventpersistence "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/persistence"
)

func TestGoldenCatalogRawValueFieldsAreExplicitlyNumericInRawIndexMapping(t *testing.T) {
	mapped := map[string]bool{}
	for _, field := range eventpersistence.ElasticsearchRawNumericExtensionFields() {
		mapped[field] = true
	}
	for _, definition := range generated.GoldenMetricCatalog {
		if definition.Source.Track != "product_telemetry" {
			continue
		}
		var required []string
		switch definition.Source.Aggregation {
		case "percentile_p95":
			required = []string{definition.Source.ValueField}
		case "sum_ratio":
			required = []string{
				definition.Source.NumeratorValueField,
				definition.Source.DenominatorValueField,
			}
		default:
			continue
		}
		for _, field := range required {
			if field == "" {
				t.Fatalf(
					"golden metric %s (%s) declares empty raw value field",
					definition.MetricID, definition.Source.Aggregation,
				)
			}
			if !mapped[field] {
				t.Errorf(
					"golden metric %s raw value field %q is missing from the explicit numeric mapping list; "+
						"it would be dynamically mapped as keyword and break ES numeric aggregations",
					definition.MetricID, field,
				)
			}
		}
	}
}
