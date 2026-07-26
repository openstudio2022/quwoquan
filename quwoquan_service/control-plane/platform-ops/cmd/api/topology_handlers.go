package main

import (
	"net/http"
	"sort"
)

// topology 端点从服务、external 和 platform 的环境 deploy 入口扫描 workload；
// 环境目标事实来自 environments/<env>/runtime.yaml；
//   - 实例事实来自 config_instance_reports（服务 config ACK 上报），
//     不再依赖无生产者的 Postgres 文档 namespace。
func deploymentTargetForEnvironment(doc environmentTopology, environment string) string {
	preferred := environment + "-local"
	if environment == "prod" {
		preferred = "prod-hosted"
	}
	if target, ok := doc.Targets[preferred]; ok && target.Environment == environment {
		return preferred
	}
	for targetID, target := range doc.Targets {
		if target.Environment == environment {
			return targetID
		}
	}
	return environment
}

func (s *platformService) handleListRuntimeClusters(w http.ResponseWriter, r *http.Request) {
	doc, err := s.readEnvironmentTopology()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0, len(doc.Environments))
	for environment, topology := range doc.Environments {
		target := deploymentTargetForEnvironment(doc, environment)
		services := make([]string, 0, len(topology.Workloads))
		for _, workload := range topology.Workloads {
			services = append(services, workload.ID)
		}
		sort.Strings(services)
		items = append(items, map[string]any{
			"id":          environment + ":" + target,
			"environment": environment,
			"cluster":     target,
			"plane":       "service-plane",
			"services":    services,
			// declared：来自部署映射声明，而非运行时探测。
			"status": "declared",
		})
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleListRuntimeServices(w http.ResponseWriter, r *http.Request) {
	doc, err := s.readEnvironmentTopology()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	instanceCounts := map[string]int{}
	for _, report := range reports {
		key := stringifyDocumentValue(report["environment"]) + "|" + stringifyDocumentValue(report["service"])
		instanceCounts[key]++
	}
	items := make([]map[string]any, 0)
	for environment, topology := range doc.Environments {
		target := deploymentTargetForEnvironment(doc, environment)
		for _, workload := range topology.Workloads {
			instances := instanceCounts[environment+"|"+workload.ID]
			status := "declared"
			if instances > 0 {
				status = "reporting"
			}
			items = append(items, map[string]any{
				"id":            environment + ":" + workload.ID,
				"environment":   environment,
				"cluster":       target,
				"service":       workload.ID,
				"plane":         workload.Plane,
				"deploymentRef": workload.DeploymentRef,
				"instances":     instances,
				"status":        status,
			})
		}
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func (s *platformService) handleListRuntimeInstances(w http.ResponseWriter, r *http.Request) {
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0, len(reports))
	for _, report := range reports {
		environment := stringifyDocumentValue(report["environment"])
		status := "drift"
		if documentBool(report["inSync"]) {
			status = "in-sync"
		}
		items = append(items, map[string]any{
			"id":          stringifyDocumentValue(report["instanceId"]),
			"environment": environment,
			"cluster":     stringifyDocumentValue(report["cluster"]),
			"service":     stringifyDocumentValue(report["service"]),
			"plane":       "service-plane",
			"status":      status,
		})
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i]["id"].(string) < items[j]["id"].(string)
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}
