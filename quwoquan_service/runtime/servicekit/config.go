package servicekit

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"

	configrelease "quwoquan_service/runtime/configrelease"
	"quwoquan_service/runtime/controlplane"
)

// LoadYAMLConfig 从 configrelease 选定的唯一渲染快照加载服务配置。
// 它从不回退到仓库内环境定义或第二套默认配置：快照缺失即失败。
func LoadYAMLConfig(identity Identity, target any) error {
	_, err := LoadYAMLConfigRaw(identity, target)
	return err
}

// ConfigPathFor 解析本次生效的渲染快照路径。它与 LoadYAMLConfigRaw 走同一条
// configrelease 选路，只是不读文件，供骨架写入 BaseConfig.ConfigPath。
func ConfigPathFor(identity Identity) (string, error) {
	return configrelease.File(identity.ConfigRoot, identity.ServiceName, identity.AppEnv)
}

// LoadYAMLConfigRaw 与 LoadYAMLConfig 同源，额外返回快照原文，供需要对快照
// 形状本身取证的服务（如拒收已退役配置段）做二次校验。
func LoadYAMLConfigRaw(identity Identity, target any) ([]byte, error) {
	path, err := configrelease.File(
		identity.ConfigRoot, identity.ServiceName, identity.AppEnv,
	)
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read generated runtime config: %w", err)
	}
	if err := yaml.Unmarshal(raw, target); err != nil {
		return nil, fmt.Errorf("parse %s: %w", path, err)
	}
	return raw, nil
}

// ValidateConfigIdentity 校验配置快照声明的版本与进程注入身份一致，并要求
// 一个不可变的 IMAGE_VERSION 发布身份。
func ValidateConfigIdentity(fileConfigVersion string, identity Identity) error {
	envVersion := strings.TrimSpace(identity.ConfigVersion)
	fileVersion := strings.TrimSpace(fileConfigVersion)
	if envVersion != "" && fileVersion != "" && fileVersion != envVersion {
		return fmt.Errorf(
			"CONFIG_VERSION mismatch: env=%s file=%s", envVersion, fileVersion,
		)
	}
	return controlplane.ValidateImageIdentity(identity.ImageVersion)
}

// DefaultClusterName 从 canonical 应用环境派生控制面 cluster 身份。
func DefaultClusterName(appEnv string) string {
	return strings.TrimSpace(appEnv) + "-control-a"
}

// resolveConfigSyncClusterName 解析实例报告与配置解析 scope 使用的 cluster
// 身份。部署面注入的 CLUSTER_NAME 优先于按环境派生的默认值：prod rollout
// 渲染器按 prod-<instance>-control-<replica> 逐副本注入它，忽略该注入会让
// 全体副本自称同一个 cluster，实例报告失去副本可分辨性。
func resolveConfigSyncClusterName(declared string, appEnv string) string {
	if name := strings.TrimSpace(declared); name != "" {
		return name
	}
	if name := strings.TrimSpace(os.Getenv("CLUSTER_NAME")); name != "" {
		return name
	}
	return DefaultClusterName(appEnv)
}
