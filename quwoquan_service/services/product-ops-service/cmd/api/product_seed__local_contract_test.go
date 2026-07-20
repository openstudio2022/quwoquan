package main

import "testing"

// seed 仅供 local_contract 测试构造 canonical 指标快照样例；生产 composition
// 不 seed 控制面状态。治理/推荐骨架 namespace 已随假数据面退场，禁止回填。
func (s *productService) seed() error {
	defaultMetricSnapshots := []metricSnapshot{
		{
			ID:          "L1:beta",
			Level:       "L1",
			Environment: "beta",
			Label:       "五栏主旅程完成率",
			Metric:      "five_tab_journey_completion_rate",
			Value:       82.4,
			Unit:        "%",
			Status:      "success",
			Trend:       "+2.1%",
			Description: "首页精品、圈子校园、实体主页、@小趣、消息承接的完整主旅程。",
		},
		{
			ID:          "L2:beta",
			Level:       "L2",
			Environment: "beta",
			Label:       "核心业务健康 CTR",
			Metric:      "core_business_ctr",
			Value:       11.8,
			Unit:        "%",
			Status:      "success",
			Trend:       "+0.6%",
			Description: "推荐、圈子、主页、评论与消息回流形成的业务健康口径。",
		},
		{
			ID:          "L3:beta:beta-control-a:product-ops-service",
			Level:       "L3",
			Environment: "beta",
			Cluster:     "beta-control-a",
			Service:     "product-ops-service",
			Label:       "product-ops 请求 P95",
			Metric:      "http_request_p95_ms",
			Value:       184,
			Unit:        "ms",
			Status:      "success",
			Trend:       "-22ms",
			Description: "产品控制面的服务 RED 指标。",
		},
		{
			ID:          "L3:beta:beta-user-a:realtime-gateway",
			Level:       "L3",
			Environment: "beta",
			Cluster:     "beta-user-a",
			Service:     "realtime-gateway",
			Label:       "gateway 错误率",
			Metric:      "http_error_rate",
			Value:       0.42,
			Unit:        "%",
			Status:      "warning",
			Trend:       "+0.08%",
			Description: "用户面入口的错误率，用于 RED 下钻。",
		},
		{
			ID:          "L4:beta:beta-control-a:product-ops-service:product-ops-service-beta-control-a-0",
			Level:       "L4",
			Environment: "beta",
			Cluster:     "beta-control-a",
			Service:     "product-ops-service",
			InstanceID:  "product-ops-service-beta-control-a-0",
			Label:       "product-ops 实例配置一致性",
			Metric:      "config_in_sync",
			Value:       1,
			Unit:        "bool",
			Status:      "success",
			Trend:       "synced",
			Description: "配置中心 desired hash 与实例 effective hash 一致。",
		},
		{
			ID:          "L4:beta:beta-control-a:platform-ops-service:platform-ops-service-beta-control-a-0",
			Level:       "L4",
			Environment: "beta",
			Cluster:     "beta-control-a",
			Service:     "platform-ops-service",
			InstanceID:  "platform-ops-service-beta-control-a-0",
			Label:       "platform-ops 实例配置一致性",
			Metric:      "config_in_sync",
			Value:       0,
			Unit:        "bool",
			Status:      "warning",
			Trend:       "disk-fallback",
			Description: "配置中心不可达时回退磁盘快照，等待重新拉齐。",
		},
	}
	otherEnvs := []struct {
		env     string
		cluster string
	}{
		{"alpha", "alpha-control-a"},
		{"gamma", "gamma-control-a"},
		{"prod", "prod-control-a"},
	}
	for _, e := range otherEnvs {
		defaultMetricSnapshots = append(defaultMetricSnapshots,
			metricSnapshot{
				ID: "L1:" + e.env, Level: "L1", Environment: e.env,
				Label: "五栏主旅程完成率", Metric: "five_tab_journey_completion_rate",
				Value: 82.4, Unit: "%", Status: "success", Trend: "+2.1%",
				Description: "首页精品、圈子校园、实体主页、@小趣、消息承接的完整主旅程。",
			},
			metricSnapshot{
				ID: "L2:" + e.env, Level: "L2", Environment: e.env,
				Label: "核心业务健康 CTR", Metric: "core_business_ctr",
				Value: 11.8, Unit: "%", Status: "success", Trend: "+0.6%",
				Description: "推荐、圈子、主页、评论与消息回流形成的业务健康口径。",
			},
			metricSnapshot{
				ID: "L3:" + e.env + ":" + e.cluster + ":product-ops-service", Level: "L3", Environment: e.env,
				Cluster: e.cluster, Service: "product-ops-service",
				Label: "product-ops 请求 P95", Metric: "http_request_p95_ms",
				Value: 184, Unit: "ms", Status: "success", Trend: "-22ms",
				Description: "产品控制面的服务 RED 指标。",
			},
			metricSnapshot{
				ID:    "L4:" + e.env + ":" + e.cluster + ":product-ops-service:product-ops-service-" + e.env + "-0",
				Level: "L4", Environment: e.env, Cluster: e.cluster,
				Service: "product-ops-service", InstanceID: "product-ops-service-" + e.env + "-0",
				Label: "product-ops 实例配置一致性", Metric: "config_in_sync",
				Value: 1, Unit: "bool", Status: "success", Trend: "synced",
				Description: "配置中心 desired hash 与实例 effective hash 一致。",
			},
		)
	}
	for _, item := range defaultMetricSnapshots {
		if err := s.putIfMissing("l1l4_metric_snapshots", item.ID, item); err != nil {
			return err
		}
	}

	return nil
}

func TestProductSeedIsIdempotentAndOnlyCoversMetricSnapshots(t *testing.T) {
	service := newTestProductService(t)
	if err := service.seed(); err != nil {
		t.Fatalf("seed product fixtures: %v", err)
	}
	if err := service.seed(); err != nil {
		t.Fatalf("replay product fixtures: %v", err)
	}
	if _, found, err := service.store.GetDocument("l1l4_metric_snapshots", "L1:beta"); err != nil {
		t.Fatalf("read seeded metric snapshot: %v", err)
	} else if !found {
		t.Fatal("missing seeded metric snapshot")
	}
	// 治理/推荐骨架 namespace 必须保持退场，防止假数据面回潮。
	for _, namespace := range []string{
		"moderation_cases", "recovery_cases", "appeal_cases", "recommendation_policies",
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
