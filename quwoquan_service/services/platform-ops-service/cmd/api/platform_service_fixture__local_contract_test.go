package main

import (
	"testing"

	"quwoquan_service/runtime/controlplane"
)

// seedTestPlatformService owns only the canonical examples required by the
// local-contract tests. Production composition must never seed control-plane
// state or load fixture data from the repository checkout.
func seedTestPlatformService(service *platformService) error {
	fixtures := map[string][]controlplane.Document{
		"governance_templates": {
			{"id": "timeout-template", "title": "默认超时模板", "status": "success"},
		},
		"runbooks": {
			{"id": "cfg-rollback-drill", "title": "配置发布回滚演练", "status": "success"},
		},
		"gate_rules": {
			{"id": "config_release_error_rate", "rule": "config_release_error_rate", "stage": "25%", "status": "success"},
		},
		"config_instance_reports": {
			{
				"id": "platform-ops-service-beta-control-a-0", "environment": "beta",
				"cluster": "beta-control-a", "service": "platform-ops-service",
				"instanceId":  "platform-ops-service-beta-control-a-0",
				"desiredHash": "expected", "effectiveHash": "stale", "inSync": false,
				"source": "config-center", "lastError": "stale configuration",
			},
		},
	}
	for namespace, documents := range fixtures {
		for _, document := range documents {
			if err := service.store.PutDocument(namespace, document["id"].(string), document); err != nil {
				return err
			}
		}
	}
	return nil
}

func TestSeedTestPlatformServiceProvidesCanonicalControlPlaneEvidence(t *testing.T) {
	service := newTestPlatformService(t)
	for namespace, id := range map[string]string{
		"governance_templates":    "timeout-template",
		"runbooks":                "cfg-rollback-drill",
		"gate_rules":              "config_release_error_rate",
		"config_instance_reports": "platform-ops-service-beta-control-a-0",
	} {
		if _, found, err := service.store.GetDocument(namespace, id); err != nil {
			t.Fatalf("read %s/%s: %v", namespace, id, err)
		} else if !found {
			t.Fatalf("missing canonical fixture %s/%s", namespace, id)
		}
	}
}
