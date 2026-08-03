package main

import (
	"strings"
)

// loadProjectionReadModels 收集全仓 projections/*.yaml 的 read_model 闭集（跨域可见），
// 与 fields entity 一起验证 canonical response_entity 的真实归属。
func (v *validator) loadProjectionReadModels() {
	v.projectionReadModels = map[string]bool{}
	for _, path := range v.source.Paths("", ".yaml") {
		if !strings.Contains("/"+path, "/projections/") {
			continue
		}
		var parsed struct {
			ReadModel        string `yaml:"read_model"`
			ClientProjection struct {
				DartClass string `yaml:"dart_class"`
			} `yaml:"client_projection"`
		}
		if v.source.Decode(path, &parsed) != nil {
			continue
		}
		if rm := strings.TrimSpace(parsed.ReadModel); rm != "" {
			v.projectionReadModels[rm] = true
		}
		// 迁移期间识别历史 client projection 名称，但它不能覆盖 response_entity。
		if dc := strings.TrimSpace(parsed.ClientProjection.DartClass); dc != "" {
			v.projectionReadModels[dc] = true
		}
	}
}
