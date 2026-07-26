package configrelease

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"
)

// File 返回由服务 config/schema.yaml 与 environments/<env>/config.yaml
// 渲染出的唯一有效配置文件。服务不得回读仓库定义，也不得再拼接 default/env/release overlay。
func File(configRoot, serviceName, environment string) (string, error) {
	root := strings.TrimSpace(configRoot)
	if root == "" {
		return "", fmt.Errorf("CONFIG_ROOT is required for generated runtime config")
	}
	path := filepath.Join(root, serviceName+".yaml")
	if _, err := os.Stat(path); err != nil {
		return "", fmt.Errorf("generated runtime config %s: %w", path, err)
	}
	return path, nil
}
