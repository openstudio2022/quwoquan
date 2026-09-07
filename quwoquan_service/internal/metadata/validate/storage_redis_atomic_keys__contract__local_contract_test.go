package validate

import (
	"os"
	"path/filepath"
	"testing"
)

func TestStorageRedisAtomicKeysAcceptSameSlotDeclaredSet(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rt:conn:fence:{identitySlot}
    key_prefix: 'rt:conn:fence:'
    hash_tag: identitySlot
    atomic_keys: &lease_keys
      - rt:conn:fence:{identitySlot}
      - rt:conn:lease:{identitySlot}:lease:{connectionDigest}
  - key: rt:conn:lease:{identitySlot}:lease:{connectionDigest}
    key_prefix: 'rt:conn:lease:'
    hash_tag: identitySlot
    atomic_keys: *lease_keys
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("same-slot atomic key issues=%+v", issues)
	}
}

func TestStorageRedisAtomicKeysRejectUnknownCrossSlotAndPrefixDrift(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rt:conn:fence:{identitySlot}
    key_prefix: 'rt:wrong:'
    hash_tag: identitySlot
    atomic_keys:
      - rt:conn:fence:{identitySlot}
      - rt:conn:lease:{otherSlot}:lease:{connectionDigest}
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	codes := map[string]bool{}
	for _, issue := range issues {
		codes[issue.Code] = true
	}
	for _, want := range []string{
		"CONTRACT.STORAGE.REDIS_KEY_PREFIX_MISMATCH",
		"CONTRACT.STORAGE.REDIS_ATOMIC_KEY_UNKNOWN",
		"CONTRACT.STORAGE.REDIS_ATOMIC_HASH_TAG_MISMATCH",
	} {
		if !codes[want] {
			t.Fatalf("issues=%+v missing %s", issues, want)
		}
	}
}

func TestStorageRedisAtomicKeysRejectExpectedTagOnlyInSecondBraceGroup(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rt:conn:fence:{identitySlot}
    hash_tag: identitySlot
    atomic_keys: &lease_keys
      - rt:conn:fence:{identitySlot}
      - rt:conn:lease:{wrongSlot}:{identitySlot}
  - key: rt:conn:lease:{wrongSlot}:{identitySlot}
    hash_tag: identitySlot
    atomic_keys: *lease_keys
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageIssueCodes(issues)["CONTRACT.STORAGE.REDIS_ATOMIC_HASH_TAG_MISMATCH"] {
		t.Fatalf("issues=%+v missing first hash-tag mismatch", issues)
	}
}

func TestRedisClusterHashTagUsesFirstNonEmptyBraceGroup(t *testing.T) {
	for key, want := range map[string]string{
		"prefix:{identitySlot}:{later}": "identitySlot",
		"prefix:{}:{identitySlot}":      "identitySlot",
		"prefix:{wrong}:{identitySlot}": "wrong",
		"prefix:{unterminated":          "",
		"prefix:no-tag":                 "",
	} {
		if got := redisClusterHashTag(key); got != want {
			t.Errorf("redisClusterHashTag(%q) = %q, want %q", key, got, want)
		}
	}
}

func writeStorageAtomicFixture(t *testing.T, metadataDir, document string) {
	t.Helper()
	objectDir := filepath.Join(metadataDir, "realtime-gateway", "realtime", "connection")
	if err := os.MkdirAll(objectDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(objectDir, "storage.yaml"), []byte(document), 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestStorageRedisAtomicKeysRejectQuotaMechanismWithoutDeclaration(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    create_operation: lua_same_quota_shard_set_nx_with_key_and_byte_admission
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_index:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageIssueCodes(issues)["CONTRACT.STORAGE.REDIS_ATOMIC_DECLARATION_REQUIRED"] {
		t.Fatalf("issues=%+v missing required atomic declaration issue", issues)
	}
}

func TestStorageRedisAtomicKeysRejectCreateOperationWithoutDeclaration(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    create_operation: lua_same_quota_shard_set_nx_with_key_and_byte_admission
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageIssueCodes(issues)["CONTRACT.STORAGE.REDIS_ATOMIC_DECLARATION_REQUIRED"] {
		t.Fatalf("issues=%+v missing create-operation declaration issue", issues)
	}
}

func TestStorageRedisAtomicKeysRejectQuotaParticipantClosedSetDrift(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    hash_tag: rfw-<quotaShard>
    atomic_keys: &quota_keys
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
      - rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    create_operation: lua_same_quota_shard_set_nx_with_key_and_byte_admission
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    hash_tag: rfw-<quotaShard>
    atomic_keys:
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    hash_tag: rfw-<quotaShard>
    atomic_keys: *quota_keys
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageIssueCodes(issues)["CONTRACT.STORAGE.REDIS_ATOMIC_SET_MISMATCH"] {
		t.Fatalf("issues=%+v missing atomic closed-set mismatch", issues)
	}
}

func TestStorageRedisAtomicKeysSchemaAcceptsTemplatedQuotaHashTag(t *testing.T) {
	t.Parallel()

	const (
		valueKey    = "rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}"
		indexKey    = "rec:ranked_feed_window_index:{rfw-<quotaShard>}"
		metadataKey = "rec:ranked_feed_window_metadata:{rfw-<quotaShard>}"
	)
	atomicKeys := []any{valueKey, indexKey, metadataKey}
	document := map[string]any{
		"backend": "redis",
		"role":    "runtime",
		"redis_cache": []any{
			map[string]any{
				"key": valueKey, "key_prefix": "rec:ranked_feed_window:",
				"hash_tag": "rfw-<quotaShard>", "atomic_keys": atomicKeys,
			},
			map[string]any{
				"key": indexKey, "key_prefix": "rec:ranked_feed_window_index:",
				"hash_tag": "rfw-<quotaShard>", "atomic_keys": atomicKeys,
			},
			map[string]any{
				"key": metadataKey, "key_prefix": "rec:ranked_feed_window_metadata:",
				"hash_tag": "rfw-<quotaShard>", "atomic_keys": atomicKeys,
			},
		},
	}
	if err := compileStorageSchema(t).Validate(document); err != nil {
		t.Fatalf("schema rejected templated quota hash tag: %v", err)
	}
}

func TestStorageRedisAtomicKeysAcceptQuotaThreeKeyClosedSet(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    key_prefix: 'rec:ranked_feed_window:'
    hash_tag: rfw-<quotaShard>
    atomic_keys: &quota_keys
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
      - rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    create_operation: lua_same_quota_shard_set_nx_with_key_and_byte_admission
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    key_prefix: 'rec:ranked_feed_window_index:'
    hash_tag: rfw-<quotaShard>
    atomic_keys: *quota_keys
  - key: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    key_prefix: 'rec:ranked_feed_window_metadata:'
    hash_tag: rfw-<quotaShard>
    atomic_keys: *quota_keys
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if len(issues) != 0 {
		t.Fatalf("valid quota three-key issues=%+v", issues)
	}
}

func TestStorageRedisAtomicKeysRejectQuotaParticipantWithoutDeclaration(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    hash_tag: rfw-<quotaShard>
    atomic_keys:
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
      - rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_index:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	declarationIssues := 0
	for _, issue := range issues {
		if issue.Code == "CONTRACT.STORAGE.REDIS_ATOMIC_DECLARATION_REQUIRED" {
			declarationIssues++
		}
	}
	if declarationIssues != 2 {
		t.Fatalf("issues=%+v declaration issues=%d, want 2 quota participants", issues, declarationIssues)
	}
}

func TestStorageRedisAtomicKeysRejectQuotaParticipantHashTagDrift(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    hash_tag: rfw-<quotaShard>
    atomic_keys: &quota_keys
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
      - rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
  - key: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    hash_tag: other-<quotaShard>
    atomic_keys: *quota_keys
  - key: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    hash_tag: rfw-<quotaShard>
    atomic_keys: *quota_keys
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	if !storageIssueCodes(issues)["CONTRACT.STORAGE.REDIS_ATOMIC_PARTICIPANT_HASH_TAG_MISMATCH"] {
		t.Fatalf("issues=%+v missing participant hash-tag mismatch", issues)
	}
}

func TestStorageRedisAtomicKeysRejectUnknownQuotaReferences(t *testing.T) {
	metadataDir := t.TempDir()
	writeStorageAtomicFixture(t, metadataDir, `backend: redis
role: runtime
redis_cache:
  - key: rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
    hash_tag: rfw-<quotaShard>
    atomic_keys:
      - rec:ranked_feed_window:{rfw-<quotaShard>}:<subjectHash>:{windowId}
      - rec:ranked_feed_window_index:{rfw-<quotaShard>}
      - rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
    quota_index: rec:ranked_feed_window_index:{rfw-<quotaShard>}
    quota_metadata: rec:ranked_feed_window_metadata:{rfw-<quotaShard>}
`)
	issues, err := storageRedisAtomicKeyIssues(metadataDir)
	if err != nil {
		t.Fatal(err)
	}
	codes := storageIssueCodes(issues)
	for _, want := range []string{
		"CONTRACT.STORAGE.REDIS_QUOTA_INDEX_UNKNOWN",
		"CONTRACT.STORAGE.REDIS_QUOTA_METADATA_UNKNOWN",
	} {
		if !codes[want] {
			t.Fatalf("issues=%+v missing %s", issues, want)
		}
	}
}

func storageIssueCodes(issues []Issue) map[string]bool {
	codes := make(map[string]bool, len(issues))
	for _, issue := range issues {
		codes[issue.Code] = true
	}
	return codes
}
