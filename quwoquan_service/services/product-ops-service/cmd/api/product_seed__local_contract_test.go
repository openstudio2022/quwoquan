package main

import "testing"

// seed 保留给既有 local_contract 的统一测试初始化入口，但不再生成任何控制面
// 指标样例。L1-L4 数值必须由真实 telemetry/Prometheus 派生，测试也通过写入
// 明确的事件和 Prometheus test double 来证明该链路。
func (s *productService) seed() error {
	return nil
}

func TestProductSeedIsIdempotentAndDoesNotCreateFakeMetricSnapshots(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed product fixtures: %v", err)
	}
	if err := service.seed(); err != nil {
		t.Fatalf("replay product fixtures: %v", err)
	}
	// L1-L4 和治理/推荐骨架 namespace 必须保持退场，防止假数据面回潮。
	for _, namespace := range []string{
		"l1l4_metric_snapshots", "moderation_cases", "recovery_cases", "appeal_cases",
		"recommendation_policies",
	} {
		items, err := service.store.ListDocuments(namespace)
		if err != nil {
			t.Fatalf("list %s: %v", namespace, err)
		}
		if len(items) != 0 {
			t.Fatalf("namespace %s must stay empty after seed, got %d items", namespace, len(items))
		}
	}
}
