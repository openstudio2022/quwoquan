package datarelease_test

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"testing"

	"quwoquan_service/runtime/datarelease"
)

func TestLoadReturnsVerifiedImmutableReleaseTuple(t *testing.T) {
	root, digest := writeReleaseFixture(t)

	tuple, err := datarelease.Load(root)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if tuple.ReleaseID != "release-20260906-001" ||
		tuple.SourceOwner != datarelease.SourceOwnerQWQData ||
		tuple.ReleaseKind != datarelease.ReleaseKindContent ||
		tuple.ReleaseClass != datarelease.ReleaseClassResearch ||
		tuple.PayloadSHA256 != datarelease.Digest(digest) {
		t.Fatalf("unexpected tuple: %+v", tuple)
	}
}

func TestLoadMatchesProducerPathBlobMerkleVector(t *testing.T) {
	root, digest := writeReleaseFixture(t)
	const producerVector = "sha256:4f16e774570b1ce55931d251c731308e2d92e263c19d5ab7842486ab48a03245"
	if digest != producerVector {
		t.Fatalf("payload digest differs from producer tree_integrity vector: got %s want %s", digest, producerVector)
	}
	tuple, err := datarelease.Load(root)
	if err != nil {
		t.Fatalf("Load vector: %v", err)
	}
	if string(tuple.PayloadSHA256) != producerVector {
		t.Fatalf("loader digest differs from producer vector: %s", tuple.PayloadSHA256)
	}
}

func TestLoadRejectsPayloadDigestDrift(t *testing.T) {
	root, _ := writeReleaseFixture(t)
	writeFile(t, filepath.Join(root, "payload", "objects", "entity.json"), []byte(`{"changed":true}`))

	_, err := datarelease.Load(root)
	assertLoadError(t, err, datarelease.CodeDigestDrift, "payloadSha256")
}

func TestLoadRejectsHeaderAttestationIdentityDrift(t *testing.T) {
	tests := []struct {
		name  string
		field string
		value any
		code  datarelease.ErrorCode
	}{
		{name: "release id", field: "releaseId", value: "other-release", code: datarelease.CodeIdentityDrift},
		{name: "source owner", field: "sourceOwner", value: "other-owner", code: datarelease.CodeInvalidField},
		{name: "release kind", field: "releaseKind", value: "empty_baseline", code: datarelease.CodeIdentityDrift},
		{name: "release class", field: "releaseClass", value: "commercial", code: datarelease.CodeIdentityDrift},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root, _ := writeReleaseFixture(t)
			mutateJSONDocument(t, filepath.Join(root, "attestations", "release.json"), func(document map[string]any) {
				document[test.field] = test.value
			})

			_, err := datarelease.Load(root)
			assertLoadError(t, err, test.code, test.field)
		})
	}
}

func TestLoadRejectsSymlinksAndPathEscape(t *testing.T) {
	t.Run("attestation points outside release root", func(t *testing.T) {
		root, _ := writeReleaseFixture(t)
		attestationPath := filepath.Join(root, "attestations", "release.json")
		raw, err := os.ReadFile(attestationPath)
		if err != nil {
			t.Fatal(err)
		}
		external := filepath.Join(t.TempDir(), "release.json")
		writeFile(t, external, raw)
		if err := os.Remove(attestationPath); err != nil {
			t.Fatal(err)
		}
		if err := os.Symlink(external, attestationPath); err != nil {
			t.Fatal(err)
		}

		_, err = datarelease.Load(root)
		assertLoadError(t, err, datarelease.CodeUnsafePath, "")
	})

	t.Run("payload closure contains symlink", func(t *testing.T) {
		root, _ := writeReleaseFixture(t)
		external := filepath.Join(t.TempDir(), "outside.json")
		writeFile(t, external, []byte(`{"outside":true}`))
		if err := os.Symlink(external, filepath.Join(root, "payload", "objects", "escape.json")); err != nil {
			t.Fatal(err)
		}

		_, err := datarelease.Load(root)
		assertLoadError(t, err, datarelease.CodeUnsafePath, "")
	})
}

func TestLoadRejectsMissingEmptyAndInvalidFields(t *testing.T) {
	tests := []struct {
		name   string
		target string
		mutate func(map[string]any)
		code   datarelease.ErrorCode
		field  string
	}{
		{
			name: "missing release class", target: "attestations/release.json",
			mutate: func(document map[string]any) { delete(document, "releaseClass") },
			code:   datarelease.CodeMissingField, field: "releaseClass",
		},
		{
			name: "empty release id", target: "attestations/release.json",
			mutate: func(document map[string]any) { document["releaseId"] = "" },
			code:   datarelease.CodeInvalidField, field: "releaseId",
		},
		{
			name: "wrong schema", target: "attestations/release.json",
			mutate: func(document map[string]any) { document["schema"] = "quwoquan_data.release" },
			code:   datarelease.CodeSchemaMismatch, field: "schema",
		},
		{
			name: "wrong digest", target: "attestations/release.json",
			mutate: func(document map[string]any) { document["payloadSha256"] = "SHA256:ABC" },
			code:   datarelease.CodeInvalidField, field: "payloadSha256",
		},
		{
			name: "wrong field type", target: "attestations/release.json",
			mutate: func(document map[string]any) { document["releaseKind"] = 7 },
			code:   datarelease.CodeInvalidField, field: "releaseKind",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			root, _ := writeReleaseFixture(t)
			mutateJSONDocument(t, filepath.Join(root, filepath.FromSlash(test.target)), test.mutate)

			_, err := datarelease.Load(root)
			assertLoadError(t, err, test.code, test.field)
		})
	}
}

func TestLoadRejectsDuplicateIdentityField(t *testing.T) {
	root, _ := writeReleaseFixture(t)
	path := filepath.Join(root, "attestations", "release.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	raw = append([]byte(`{"releaseId":"shadow",`), raw[1:]...)
	writeFile(t, path, raw)

	_, err = datarelease.Load(root)
	assertLoadError(t, err, datarelease.CodeInvalidJSON, "releaseId")
}

func assertLoadError(t *testing.T, err error, code datarelease.ErrorCode, field string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected %s", code)
	}
	var loadErr *datarelease.LoadError
	if !errors.As(err, &loadErr) {
		t.Fatalf("expected *datarelease.LoadError, got %T: %v", err, err)
	}
	if loadErr.Code != code || (field != "" && loadErr.Field != field) {
		t.Fatalf("unexpected load error: %+v", loadErr)
	}
	if !datarelease.HasCode(err, code) {
		t.Fatalf("HasCode(%s) returned false", code)
	}
}

func writeReleaseFixture(t *testing.T) (string, string) {
	t.Helper()
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "payload", "objects"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(filepath.Join(root, "attestations"), 0o755); err != nil {
		t.Fatal(err)
	}
	header := map[string]any{
		"schema":       datarelease.HeaderSchema,
		"releaseId":    "release-20260906-001",
		"sourceOwner":  string(datarelease.SourceOwnerQWQData),
		"releaseKind":  string(datarelease.ReleaseKindContent),
		"releaseClass": string(datarelease.ReleaseClassResearch),
	}
	writeJSONDocument(t, filepath.Join(root, "payload", "release.json"), header)
	writeFile(t, filepath.Join(root, "payload", "objects", "entity.json"), []byte(`{"entityRef":"地点/景区/测试"}`))
	digest := payloadDigest(t, filepath.Join(root, "payload"))
	attestation := map[string]any{
		"schema":        datarelease.AttestationSchema,
		"releaseId":     "release-20260906-001",
		"sourceOwner":   string(datarelease.SourceOwnerQWQData),
		"releaseKind":   string(datarelease.ReleaseKindContent),
		"releaseClass":  string(datarelease.ReleaseClassResearch),
		"payloadSha256": digest,
	}
	writeJSONDocument(t, filepath.Join(root, "attestations", "release.json"), attestation)
	return root, digest
}

func mutateJSONDocument(t *testing.T, path string, mutate func(map[string]any)) {
	t.Helper()
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(raw, &document); err != nil {
		t.Fatal(err)
	}
	mutate(document)
	writeJSONDocument(t, path, document)
}

func writeJSONDocument(t *testing.T, path string, document map[string]any) {
	t.Helper()
	raw, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	writeFile(t, path, append(raw, '\n'))
}

func writeFile(t *testing.T, path string, raw []byte) {
	t.Helper()
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
}

type testPayloadEntry struct {
	path string
	leaf [sha256.Size]byte
}

func payloadDigest(t *testing.T, root string) string {
	t.Helper()
	entries := make([]testPayloadEntry, 0)
	if err := filepath.WalkDir(root, func(path string, entry os.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return err
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		blobHash := sha256.Sum256(raw)
		blobDigest := "sha256:" + hex.EncodeToString(blobHash[:])
		relative = filepath.ToSlash(relative)
		leaf := sha256.Sum256([]byte(fmt.Sprintf("blob\x00%s\x00%s\x00%s", relative, blobDigest, strconv.Itoa(len(raw)))))
		entries = append(entries, testPayloadEntry{path: relative, leaf: leaf})
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	sort.Slice(entries, func(left, right int) bool { return entries[left].path < entries[right].path })
	level := make([][sha256.Size]byte, len(entries))
	for index := range entries {
		level[index] = entries[index].leaf
	}
	if len(level) == 0 {
		empty := sha256.Sum256(nil)
		return "sha256:" + hex.EncodeToString(empty[:])
	}
	for len(level) > 1 {
		next := make([][sha256.Size]byte, 0, (len(level)+1)/2)
		for index := 0; index < len(level); index += 2 {
			right := level[index]
			if index+1 < len(level) {
				right = level[index+1]
			}
			input := append([]byte("node\x00"), level[index][:]...)
			input = append(input, right[:]...)
			next = append(next, sha256.Sum256(input))
		}
		level = next
	}
	return "sha256:" + hex.EncodeToString(level[0][:])
}
