package validate

import (
	"io/fs"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/storagecontract"
)

// transactionMechanismGuaranteeVocabulary 是 storage.yaml transaction.mechanism 与
// guarantees 词表的对应闭集，由仓内已声明 mechanism 的 storage.yaml 归纳得出：
//
//   - version_cas：至少一条 guarantee 以 _cas 结尾（aggregate_version_cas、
//     *_revision_cas、version_cas）。
//   - unique_constraint：至少一条 guarantee 含 unique（*_unique_winner、
//     *_unique_dedupe）。
//   - fence：至少一条 guarantee 含 fence（*_fence、*_fencing）。
//   - conditional_update：至少一条 guarantee 含 conditional、serialization、
//     monotonic 或 atomic_commit（条件更新/序列化窗口/单调序号）。
//
// mechanism 说的是「靠什么裁决并发」，guarantees 说的是「裁决出什么结果」；
// 两者词表对不上就说明其中一处是期望而不是实现。
var transactionMechanismGuaranteeVocabulary = map[string]func(guarantee string) bool{
	"version_cas": func(guarantee string) bool {
		return strings.HasSuffix(guarantee, "_cas")
	},
	"unique_constraint": func(guarantee string) bool {
		return strings.Contains(guarantee, "unique")
	},
	"fence": func(guarantee string) bool {
		return strings.Contains(guarantee, "fence")
	},
	"conditional_update": func(guarantee string) bool {
		return strings.Contains(guarantee, "conditional") ||
			strings.Contains(guarantee, "serialization") ||
			strings.Contains(guarantee, "monotonic") ||
			strings.Contains(guarantee, "atomic_commit")
	},
}

// storageTransactionMechanismIssues 要求 transaction.mechanism 与 guarantees 词表
// 一致。mechanism 的取值闭集由 storage.schema.json 拥有；未声明 mechanism 的事务
// 不在此判定（schema 未将其列为 required）。
func storageTransactionMechanismIssues(metadataDir string) ([]Issue, error) {
	var issues []Issue
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" {
			return nil
		}
		document, loadErr := storagecontract.LoadOptional(path)
		if loadErr != nil || document == nil || document.Transaction == nil {
			return nil
		}
		mechanism := strings.TrimSpace(document.Transaction.Mechanism)
		if mechanism == "" {
			return nil
		}
		matches, known := transactionMechanismGuaranteeVocabulary[mechanism]
		if !known {
			// 未知取值由 schema enum 拥有。
			return nil
		}
		for _, guarantee := range document.Transaction.Guarantees {
			if matches(strings.TrimSpace(guarantee)) {
				return nil
			}
		}
		guarantees := append([]string(nil), document.Transaction.Guarantees...)
		sort.Strings(guarantees)
		issues = append(issues, issue(
			"CONTRACT.STORAGE.TRANSACTION_MECHANISM_GUARANTEE_MISMATCH",
			relativeMetadataPath(metadataDir, path),
			"transaction.mechanism %q has no matching guarantee in [%s]",
			mechanism, strings.Join(guarantees, ", "),
		))
		return nil
	})
	if err != nil {
		return nil, err
	}
	sortIssues(issues)
	return issues, nil
}
