package validate

import (
	"io/fs"
	"os"
	"path/filepath"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"
)

// storageTransactionScopeIssues 保证 scope 只引用当前对象的资源，而跨对象参与者
// 必须指向同 service/context 下兄弟对象实际声明的 collection。这样 contract 不会把
// 期望的跨对象原子性伪装成不存在的本地 collection。
func storageTransactionScopeIssues(metadataDir string) ([]Issue, error) {
	type storageEntry struct {
		sourcePath string
		service    string
		context    string
		object     string
		document   ast.StorageDocument
	}
	var entries []storageEntry
	err := filepath.WalkDir(metadataDir, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" {
			return nil
		}
		segments := strings.Split(filepath.ToSlash(relativeMetadataPath(metadataDir, path)), "/")
		if len(segments) != 4 {
			return nil
		}
		data, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		document, err := storagecontract.DecodeYAML(data)
		if err != nil {
			return nil // closed schema/typed-reader validation owns malformed documents
		}
		entries = append(entries, storageEntry{
			sourcePath: strings.Join(segments, "/"), service: segments[0],
			context: segments[1], object: segments[2], document: document,
		})
		return nil
	})
	if err != nil {
		return nil, err
	}

	byObject := make(map[string]storageEntry, len(entries))
	for _, entry := range entries {
		byObject[strings.Join([]string{entry.service, entry.context, entry.object}, "/")] = entry
	}
	var issues []Issue
	for _, entry := range entries {
		if entry.document.Transaction == nil {
			continue
		}
		for _, resource := range entry.document.Transaction.Scope {
			if _, collection := entry.document.Collections[resource]; !collection {
				if _, table := entry.document.Tables[resource]; !table {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.TRANSACTION_SCOPE_UNKNOWN",
						entry.sourcePath,
						"transaction scope %q is not declared by this storage document",
						resource,
					))
				}
			}
		}
		seenObjects := map[string]struct{}{}
		for _, participant := range entry.document.Transaction.Participants {
			participantObject := strings.TrimSpace(participant.Object)
			if participantObject == entry.object {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_SELF",
					entry.sourcePath,
					"transaction participant %q must use local scope instead",
					participantObject,
				))
				continue
			}
			if _, duplicate := seenObjects[participantObject]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_DUPLICATE",
					entry.sourcePath,
					"transaction participant %q is declared more than once",
					participantObject,
				))
				continue
			}
			seenObjects[participantObject] = struct{}{}
			key := strings.Join([]string{entry.service, entry.context, participantObject}, "/")
			owner, found := byObject[key]
			if !found {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_UNKNOWN",
					entry.sourcePath,
					"transaction participant %q is not a sibling object in service/context %s/%s",
					participantObject, entry.service, entry.context,
				))
				continue
			}
			if owner.document.Backend != entry.document.Backend {
				issues = append(issues, issue(
					"CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_BACKEND_MISMATCH",
					entry.sourcePath,
					"transaction participant %q backend %q differs from owner backend %q",
					participantObject, owner.document.Backend, entry.document.Backend,
				))
				continue
			}
			for _, collection := range participant.Collections {
				if _, found := owner.document.Collections[collection]; !found {
					issues = append(issues, issue(
						"CONTRACT.STORAGE.TRANSACTION_PARTICIPANT_COLLECTION_UNKNOWN",
						entry.sourcePath,
						"transaction participant %q does not declare collection %q",
						participantObject, collection,
					))
				}
			}
		}
	}
	return issues, nil
}
