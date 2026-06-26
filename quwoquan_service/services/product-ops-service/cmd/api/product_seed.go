package main

func (s *productService) seed() error {
	defaultExperiments := []experimentDef{
		{
			ID:            "discovery_feed_v3",
			Name:          "发现流排序权重调优",
			Enabled:       true,
			PolicyVersion: "ops-2026.03.08",
			Buckets: []bucketDef{
				{Name: "control", WeightPct: 50},
				{Name: "variant_a", WeightPct: 25},
				{Name: "variant_b", WeightPct: 25},
			},
			BucketStats: map[string]int{},
			Assignments: map[string]assignment{},
		},
		{
			ID:            "new_user_recall_mix",
			Name:          "新用户召回混排实验",
			Enabled:       true,
			PolicyVersion: "ops-2026.03.08",
			Buckets: []bucketDef{
				{Name: "control", WeightPct: 70},
				{Name: "boosted_recall", WeightPct: 30},
			},
			BucketStats: map[string]int{},
			Assignments: map[string]assignment{},
		},
	}
	for _, item := range defaultExperiments {
		if err := s.putIfMissing("experiments", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("experiment", item.ID, "experiment_rollout_v1", "running"); err != nil {
			return err
		}
	}

	defaultModerationCases := []moderationCase{
		{
			ID:            "case_post_901",
			TargetType:    "post",
			TargetID:      "post_901",
			Reason:        "spam",
			Status:        "reported",
			AssignedQueue: "content-moderation",
			EvidenceRefs:  []string{"evidence_img_1"},
			UpdatedAt:     nowRFC3339(),
		},
	}
	for _, item := range defaultModerationCases {
		if err := s.putIfMissing("moderation_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("moderation_case", item.ID, "moderation_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultRecoveryCases := []recoveryCase{
		{
			ID:           "recovery_user_1827",
			UserID:       "user_1827",
			Status:       "evidence_verified",
			EvidenceRefs: []string{"device_proof", "payment_receipt"},
			UpdatedAt:    nowRFC3339(),
		},
	}
	for _, item := range defaultRecoveryCases {
		if err := s.putIfMissing("recovery_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("recovery_case", item.ID, "recovery_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultAppealCases := []appealCase{
		{
			ID:           "appeal_case_301",
			TargetType:   "account",
			TargetID:     "user_1827",
			Status:       "under_review",
			EvidenceRefs: []string{"appeal_form", "chat_snapshot"},
			UpdatedAt:    nowRFC3339(),
		},
	}
	for _, item := range defaultAppealCases {
		if err := s.putIfMissing("appeal_cases", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("appeal_case", item.ID, "appeal_case_v1", item.Status); err != nil {
			return err
		}
	}

	defaultPolicies := []recommendationPolicy{
		{
			ID:            "policy_discovery_rank_v12",
			Name:          "发现流重排策略 v12",
			Status:        "simulated",
			PolicyVersion: "policy-2026.03.08",
			GuardrailSnapshot: map[string]any{
				"ctr":        8.9,
				"complaints": 0.29,
				"diversity":  69,
			},
			UpdatedAt: nowRFC3339(),
		},
	}
	for _, item := range defaultPolicies {
		if err := s.putIfMissing("recommendation_policies", item.ID, item); err != nil {
			return err
		}
		if err := s.putWorkflowIfMissing("recommendation_policy", item.ID, "recommendation_policy_v1", item.Status); err != nil {
			return err
		}
	}

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
