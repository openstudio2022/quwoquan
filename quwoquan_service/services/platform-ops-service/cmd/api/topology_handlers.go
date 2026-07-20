package main

import (
	"net/http"
	"path/filepath"
	"sort"
	"strings"
)

// topology 端点的唯一真相源：
//   - 环境/服务声明来自 quwoquan_ops/environments/process_domain_mapping.yaml；
//   - plane 归属来自 process_domain_plane_mapping.yaml；
//   - 实例事实来自 config_instance_reports（服务 config ACK 上报），
//     不再依赖无生产者的 Postgres 文档 namespace。
var environmentDeploymentTargets = map[string]string{
	"dev":   "dev-local",
	"alpha": "alpha-local",
	"beta":  "beta-local",
	"gamma": "gamma-local",
	"prod":  "prod-hosted",
}

type processDomainMappingDoc struct {
	Environments map[string]map[string]struct {
		Domains []string `yaml:"domains"`
	} `yaml:"environments"`
}

type processPlaneMappingDoc struct {
	Environments map[string]map[string]struct {
		Bindings []struct {
			Domain string   `yaml:"domain"`
			Planes []string `yaml:"planes"`
		} `yaml:"bindings"`
	} `yaml:"environments"`
}

func (s *platformService) readProcessDomainMapping() (processDomainMappingDoc, error) {
	var doc processDomainMappingDoc
	err := s.readYAMLInto(
		filepath.Join(s.repoRoot, "quwoquan_ops", "environments", "process_domain_mapping.yaml"),
		&doc,
	)
	return doc, err
}

func (s *platformService) readProcessPlaneMapping() (processPlaneMappingDoc, error) {
	var doc processPlaneMappingDoc
	err := s.readYAMLInto(
		filepath.Join(s.repoRoot, "quwoquan_ops", "environments", "process_domain_plane_mapping.yaml"),
		&doc,
	)
	return doc, err
}

func deploymentTargetForEnvironment(environment string) string {
	if target, ok := environmentDeploymentTargets[environment]; ok {
		return target
	}
	return environment
}

func (s *platformService) handleListRuntimeClusters(w http.ResponseWriter, r *http.Request) {
	doc, err := s.readProcessDomainMapping()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	items := make([]map[string]any, 0, len(doc.Environments))
	for environment, processes := range doc.Environments {
		target := deploymentTargetForEnvironment(environment)
		services := make([]string, 0, len(processes))
		for process := range processes {
			services = append(services, process)
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
	doc, err := s.readProcessDomainMapping()
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	planeDoc, err := s.readProcessPlaneMapping()
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
	for environment, processes := range doc.Environments {
		target := deploymentTargetForEnvironment(environment)
		for process := range processes {
			planes := make([]string, 0, 2)
			if envPlanes, ok := planeDoc.Environments[environment]; ok {
				if binding, ok := envPlanes[process]; ok {
					seen := map[string]bool{}
					for _, entry := range binding.Bindings {
						for _, plane := range entry.Planes {
							if !seen[plane] {
								seen[plane] = true
								planes = append(planes, plane)
							}
						}
					}
				}
			}
			sort.Strings(planes)
			instances := instanceCounts[environment+"|"+process]
			status := "declared"
			if instances > 0 {
				status = "reporting"
			}
			items = append(items, map[string]any{
				"id":          environment + ":" + process,
				"environment": environment,
				"cluster":     target,
				"service":     process,
				"plane":       strings.Join(planes, " / "),
				"instances":   instances,
				"status":      status,
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
