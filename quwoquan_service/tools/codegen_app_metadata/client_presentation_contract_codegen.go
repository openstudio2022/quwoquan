package main

import (
	"fmt"
	"path/filepath"
	"strings"

	"quwoquan_service/tools/internal/presentationcontract"
)

func writeClientPresentationContractDartOrExit(appDir, metadataDir string) {
	if err := writeClientPresentationContractDart(appDir, metadataDir); err != nil {
		exitErr(err)
	}
}

// writeClientPresentationContractDart 在既有 domain models/request parts 完成后调用。
// helper 属 App runtime；DTO/enums 仍只归 cloud contracts，避免为 crypto 扩大纯 ABI 包依赖。
func writeClientPresentationContractDart(appDir, metadataDir string) error {
	raw, err := readMetadataDocument(filepath.Join(metadataDir, "_shared/types.yaml"))
	if err != nil {
		return err
	}
	model, err := presentationcontract.Load(raw)
	if err != nil {
		return err
	}
	owner, err := clientPresentationDartOwner()
	if err != nil {
		return err
	}
	content, err := model.RenderDart(owner, canonicalDartEnumMemberName)
	if err != nil {
		return err
	}
	writeFile(runtimeTransportSharedOutputPath(appDir, "client_content_presentation_contract.g.dart"), content)
	return nil
}

// 从本轮 renderer 内存产物定位唯一真实 DTO；不回读输出文件，不维护第二 owner 表。
func clientPresentationDartOwner() (string, error) {
	var owner string
	const prefix = "packages/quwoquan_cloud_contracts/lib/"
	for path, output := range generatedManifestOutputs {
		if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, ".dart") {
			continue
		}
		if !strings.Contains(output.Content, "class ClientContentPresentationContract {") {
			continue
		}
		found := strings.TrimPrefix(path, prefix)
		for _, line := range strings.Split(output.Content, "\n") {
			if !strings.HasPrefix(line, "part of ") {
				continue
			}
			relative := strings.Trim(strings.TrimSuffix(strings.TrimPrefix(line, "part of "), ";"), "'\"")
			found = filepath.ToSlash(filepath.Join(filepath.Dir(found), relative))
		}
		if owner != "" {
			return "", fmt.Errorf("ClientContentPresentationContract has multiple cloud DTO owners")
		}
		owner = "package:quwoquan_cloud_contracts/" + found
	}
	if owner == "" {
		return "", fmt.Errorf("ClientContentPresentationContract has no generated cloud DTO owner")
	}
	return owner, nil
}
