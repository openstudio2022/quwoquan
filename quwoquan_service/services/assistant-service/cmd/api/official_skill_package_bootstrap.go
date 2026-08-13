package bootstrap

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	skillcatalogactive "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/activerelease"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packageports "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/ports"
	packageartifact "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/artifact"
)

// bootstrapOfficialSkillPackage 在迁移阶段把官方 Skill package 激活收敛到
// candidate 挂载的签名 publication:空环境首次激活,candidate 更迭后受控
// 升级,已收敛时零写入。全程走与 skill-package-publish 相同的
// Stage+Activate 校验链(Ed25519 验签、release digest、评测 receipt),
// 不绕过任何门禁;失败 fail-closed。
//
// 没有这一步,readiness 的 active-package 检查在空环境会与环境启动互相
// 死锁(up 等健康、健康等激活、激活工具等栈启动);candidate 更迭后旧
// 激活指向的资产也会随旧 candidate 退役而无法解析。
func bootstrapOfficialSkillPackage(
	ctx context.Context,
	service *packageapplication.Service,
	activations packageports.ActivationStore,
	assetRoot string,
) error {
	if service == nil || activations == nil {
		return errors.New("assistant Skill package bootstrap dependencies are required")
	}
	reference, referenceErr := discoverOfficialPublicationRef(assetRoot)
	if referenceErr != nil {
		// 没有挂载 publication 时,已可解析的激活保持现状(兼容仅靠
		// publisher 流程管理激活的环境);既无 publication 又无可解析
		// 激活则 fail-closed,给出明确修复指引。
		if _, resolveErr := service.ResolveActive(
			ctx,
			skillcatalogactive.OfficialPackageID,
		); resolveErr == nil {
			return nil
		}
		return referenceErr
	}
	publication, err := packageartifact.LoadPublicationArtifact(assetRoot, reference)
	if err != nil {
		return fmt.Errorf("load official Skill package publication: %w", err)
	}
	activation, found, err := activations.GetActivation(
		ctx,
		skillcatalogactive.OfficialPackageID,
	)
	if err != nil {
		return fmt.Errorf("read official Skill package activation: %w", err)
	}
	if found && activation.ActiveReleaseDigest == publication.Release.ReleaseDigest {
		// 激活已收敛到挂载 publication:零写入。
		return nil
	}
	expectedRevision := publication.ExpectedRevision
	if found {
		// candidate 更迭后的受控升级:以当前指针 revision 做 CAS。
		expectedRevision = activation.Revision
	}
	staged, err := service.Stage(
		ctx,
		publication.CommandID+":stage",
		publication.Release,
	)
	if err != nil {
		return fmt.Errorf("stage official Skill package release: %w", err)
	}
	if _, err := service.Activate(
		ctx,
		publication.CommandID+":activate",
		packageapplication.ActivateInput{
			PackageID:         staged.Release.PackageID,
			ReleaseDigest:     staged.Release.ReleaseDigest,
			ExpectedRevision:  expectedRevision,
			ActivatedBy:       publication.ActivatedBy,
			EvaluationReceipt: publication.EvaluationReceipt,
		},
	); err != nil {
		return fmt.Errorf("activate official Skill package release: %w", err)
	}
	return nil
}

// discoverOfficialPublicationRef 在 release root 下发现恰好一个 publication
// 产物(releases/<buildID>/publication.json)。零个或多个都 fail-closed:
// 零个说明部署缺少 skill-package-build 产物挂载;多个必须显式指定,禁止
// 隐式挑选。
func discoverOfficialPublicationRef(assetRoot string) (string, error) {
	root := strings.TrimSpace(assetRoot)
	if root == "" {
		return "", errors.New("official Skill package release root is not configured")
	}
	releasesDir := filepath.Join(root, "releases")
	entries, err := os.ReadDir(releasesDir)
	if err != nil {
		if os.IsNotExist(err) {
			return "", fmt.Errorf(
				"official Skill package activation is absent and no publication "+
					"artifact is mounted under %s; package the environment with the "+
					"skill-package-build output before startup",
				releasesDir,
			)
		}
		return "", fmt.Errorf("scan official Skill package releases: %w", err)
	}
	references := make([]string, 0, 1)
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		candidate := filepath.Join(releasesDir, entry.Name(), "publication.json")
		info, statErr := os.Stat(candidate)
		if statErr != nil || info.IsDir() {
			continue
		}
		references = append(
			references,
			filepath.ToSlash(filepath.Join("releases", entry.Name(), "publication.json")),
		)
	}
	if len(references) == 0 {
		return "", fmt.Errorf(
			"official Skill package activation is absent and no publication "+
				"artifact exists under %s; package the environment with the "+
				"skill-package-build output before startup",
			releasesDir,
		)
	}
	if len(references) > 1 {
		return "", fmt.Errorf(
			"official Skill package bootstrap requires exactly one publication; found %d under %s",
			len(references),
			releasesDir,
		)
	}
	return references[0], nil
}
