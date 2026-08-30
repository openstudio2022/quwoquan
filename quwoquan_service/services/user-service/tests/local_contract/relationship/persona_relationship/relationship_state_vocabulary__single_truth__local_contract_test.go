// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001.t2
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-001.t3
package local_contract

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

// relationStateVocabulary 是 SIT-001 点名的五个取值，顺序无关。
var relationStateVocabulary = map[string]struct{}{
	"self":          {},
	"not_following": {},
	"following":     {},
	"followed_by":   {},
	"mutual":        {},
}

// SIT-001.t1：五值词表是关系状态的唯一出口。
// 穷举 IsFollowing / IsFollowedBy / IsMutual / IsBlocked / IsBlockedBy 的全部
// 布尔组合，确保没有任何一组事实能把第六个取值挤出来——只挑几组代表值时，
// 新增一个分支就能悄悄产生新词而测试仍然全绿。
func TestRelationStateNeverEscapesTheFiveValueVocabulary(t *testing.T) {
	t.Parallel()

	for combination := 0; combination < 32; combination++ {
		state := relmodel.RelationshipState{
			IsFollowing:  combination&1 != 0,
			IsFollowedBy: combination&2 != 0,
			IsMutual:     combination&4 != 0,
			IsBlocked:    combination&8 != 0,
			IsBlockedBy:  combination&16 != 0,
		}
		for _, pair := range [][2]string{
			{"viewer", "target"},
			{"viewer", "viewer"},
			{" viewer ", "viewer"},
		} {
			got := state.RelationState(pair[0], pair[1])
			if _, ok := relationStateVocabulary[got]; !ok {
				t.Fatalf("relation state %q escapes the five-value vocabulary (state=%+v, pair=%v)", got, state, pair)
			}
		}
	}

	// 能力矩阵与会话入口消费的是同一个词表，不允许自己再造一套。
	for combination := 0; combination < 8; combination++ {
		capability := relmodel.DeriveRelationshipCapability(relmodel.RelationshipCapabilityFacts{
			ViewerPersonaID: "viewer",
			TargetPersonaID: "target",
			Relationship: relmodel.RelationshipState{
				IsFollowing:  combination&1 != 0,
				IsFollowedBy: combination&2 != 0,
				IsMutual:     combination&4 != 0,
			},
		})
		if _, ok := relationStateVocabulary[capability.RelationState]; !ok {
			t.Fatalf("capability relation state %q escapes the vocabulary", capability.RelationState)
		}
	}
}

// SIT-001.t2：旧关系等级字段不得作为关系语义留在生产路径上。
// 扫描而不是只查一两个已知点：残留通常出现在没人再看的适配层里。
func TestNoLegacyRelationshipTierFieldSurvivesInProductionPaths(t *testing.T) {
	t.Parallel()

	root := repositoryRootFromTest(t)
	// 这些名字一旦重新出现，就意味着关系语义被第二套等级概念分叉了。
	forbidden := []string{
		"relationshipTier",
		"relationship_tier",
		"RelationshipTier",
		"friendLevel",
		"friend_level",
		"FriendLevel",
		"intimacyLevel",
		"intimacy_level",
		"IntimacyLevel",
	}
	scanned := 0
	for _, relative := range []string{
		"quwoquan_service/services/user-service/internal/relationship/persona_relationship",
		"quwoquan_service/services/user-service/contracts/relationship",
		"quwoquan_service/services/chat-service/contracts/chat",
		"quwoquan_app/lib/service/user_service/persona_management",
	} {
		base := filepath.Join(root, relative)
		if _, err := os.Stat(base); err != nil {
			continue
		}
		err := filepath.Walk(base, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() {
				return err
			}
			switch filepath.Ext(path) {
			case ".go", ".dart", ".yaml", ".yml", ".json":
			default:
				return nil
			}
			body, readErr := os.ReadFile(path)
			if readErr != nil {
				return readErr
			}
			scanned++
			for _, name := range forbidden {
				if strings.Contains(string(body), name) {
					t.Errorf("%s still carries legacy relationship tier field %q", path, name)
				}
			}
			return nil
		})
		if err != nil {
			t.Fatalf("walk %s: %v", base, err)
		}
	}
	if scanned == 0 {
		t.Fatal("scanned no files; the guard would pass vacuously")
	}
}

// SIT-001.t3：mutual 是双向 FollowEdge 的派生结论，不是可独立持久化的实体。
func TestMutualIsDerivedFromBothFollowEdgesAndNeverPersistedSeparately(t *testing.T) {
	t.Parallel()

	root := repositoryRootFromTest(t)
	store, err := os.ReadFile(filepath.Join(root,
		"quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence/pg_persona_relationship_store.go"))
	if err != nil {
		t.Fatalf("read store: %v", err)
	}
	source := string(store)
	if !strings.Contains(source, "IsMutual:     viewer.Following && target.Following") {
		t.Fatal("mutual must be computed from both directions at read time")
	}
	// 派生结论不得反向落库：一旦出现写列，就多出一个可与 FollowEdge 冲突的真相源。
	for _, persisted := range []string{"is_mutual", "mutual_since", "mutual_at", "MutualEdge", "mutual_edge"} {
		if strings.Contains(source, persisted) {
			t.Errorf("store persists derived mutual state via %q", persisted)
		}
	}

	migrations := filepath.Join(root, "quwoquan_service/services/user-service/deploy")
	if _, statErr := os.Stat(migrations); statErr == nil {
		walkErr := filepath.Walk(migrations, func(path string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || filepath.Ext(path) != ".sql" {
				return err
			}
			body, readErr := os.ReadFile(path)
			if readErr != nil {
				return readErr
			}
			for _, persisted := range []string{"is_mutual", "mutual_since", "mutual_edge"} {
				if strings.Contains(strings.ToLower(string(body)), persisted) {
					t.Errorf("%s declares a persisted mutual column %q", path, persisted)
				}
			}
			return nil
		})
		if walkErr != nil {
			t.Fatalf("walk migrations: %v", walkErr)
		}
	}

	// 领域侧同样只把 mutual 当读出来的位，不提供单独的置位入口。
	domain, err := os.ReadFile(filepath.Join(root,
		"quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model/persona_relationship.go"))
	if err != nil {
		t.Fatalf("read domain model: %v", err)
	}
	for _, setter := range []string{"func (s *RelationshipState) SetMutual", "func MarkMutual", "CommandMutual"} {
		if strings.Contains(string(domain), setter) {
			t.Errorf("domain exposes a direct mutual mutation entry %q", setter)
		}
	}
}

func repositoryRootFromTest(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "specs", "feature-tree")); statErr == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("repository root not found from test working directory")
		}
		dir = parent
	}
}
