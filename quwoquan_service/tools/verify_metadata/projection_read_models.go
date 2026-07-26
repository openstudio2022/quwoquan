package main

import (
	"strings"
)

// loadProjectionReadModels 收集全仓 projections/*.yaml 的 read_model 闭集（跨域可见），
// 作为 operations.yaml operation response_body 的唯一指向性真相源。
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
		// 兼容 response_body 直接指向 client_projection.dart_class 的写法。
		if dc := strings.TrimSpace(parsed.ClientProjection.DartClass); dc != "" {
			v.projectionReadModels[dc] = true
		}
	}
}
