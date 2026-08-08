// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-001
package local_contract

import (
	"reflect"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/compiler"
	"quwoquan_service/internal/testsupport/contractsview"
	"quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

func TestUserAccountLifecycleUsesAccountStateAsItsOnlyRuntimeState(t *testing.T) {
	profileType := reflect.TypeOf(model.UserProfile{})
	if _, exists := profileType.FieldByName("AccountState"); !exists {
		t.Fatal("generated UserAccount must expose canonical AccountState")
	}
	if _, exists := profileType.FieldByName("Status"); exists {
		t.Fatal("generated UserAccount must not reintroduce retired Status")
	}
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-002
func TestUserAccountLifecycleAndPrivacyUseCanonicalContractVocabulary(t *testing.T) {
	t.Parallel()

	contractGraph, err := compiler.Build(contractsview.Build(t))
	if err != nil {
		t.Fatalf("compile ContractGraph: %v", err)
	}

	account := requireObjectGovernance(t, contractGraph.Governance.Objects, "user.user_account")
	if account.Lifecycle == nil || account.Lifecycle.StateField != "accountState" {
		t.Fatalf("user account lifecycle = %+v, want accountState", account.Lifecycle)
	}
	if !reflect.DeepEqual(
		account.Lifecycle.States,
		[]string{"anonymous", "active", "suspended", "closed"},
	) {
		t.Fatalf("user account lifecycle states = %v", account.Lifecycle.States)
	}
	if account.Privacy == nil || account.Privacy.ObjectID != "user.user_account" {
		t.Fatalf("user account privacy owner = %+v", account.Privacy)
	}
	for field, want := range map[string]struct {
		classification ast.PrivacyClassification
		action         ast.PrivacyAppLogAction
	}{
		"birthDate": {ast.PrivacyClassificationPII, ast.PrivacyAppLogDrop},
		"region":    {ast.PrivacyClassificationPII, ast.PrivacyAppLogMask},
	} {
		policy := requirePrivacyAppLogPolicy(t, account.Privacy.Document.AppLogPolicy, field)
		if policy.Classification != want.classification || policy.AppLog != want.action {
			t.Fatalf(
				"privacy app-log policy for %q = classification %q/action %q, want %q/%q",
				field,
				policy.Classification,
				policy.AppLog,
				want.classification,
				want.action,
			)
		}
	}
	if account.Privacy.Document.DataLifecycle == nil {
		t.Fatal("user account privacy data lifecycle is missing")
	}
	// 注销级联策略的真相源是 privacy.yaml：persona 与 credential_binding 的行被
	// 内容、社交关系与风控留痕引用，物理删除会造成悬挂引用，因此按 REQ-004
	// 「任何实际保留事实必须不可逆匿名化」保留行并原地不可逆覆写个人数据；
	// 设备注册与用户设置无外部引用，整行物理删除。
	for target, wantStrategy := range map[string]ast.PrivacyDeletionStrategy{
		"user.persona":             ast.PrivacyDeletionScrub,
		"user.credential_binding":  ast.PrivacyDeletionScrub,
		"user.device_registration": ast.PrivacyDeletionHardDelete,
		"user.user_settings":       ast.PrivacyDeletionHardDelete,
	} {
		cascade := requirePrivacyDeletionCascade(
			t,
			account.Privacy.Document.DataLifecycle.DeletionCascade,
			target,
		)
		if cascade.Strategy != wantStrategy {
			t.Fatalf(
				"privacy deletion cascade for %q uses %q, want %q",
				target,
				cascade.Strategy,
				wantStrategy,
			)
		}
		// scrub 与 soft_delete 的合规姿态不同、不得互相替代；选 scrub 必须写明
		// 保留行的正当动因与被覆写的字段范围，否则保留行就是无理由的数据滞留。
		if cascade.Strategy == ast.PrivacyDeletionScrub &&
			strings.TrimSpace(cascade.Description) == "" {
			t.Fatalf(
				"privacy deletion cascade for %q scrubs without stating why the row is kept",
				target,
			)
		}
	}

	accountState := requireEnum(t, contractGraph.Governance.Enums, "AccountState")
	if !reflect.DeepEqual(
		accountState.Values,
		[]string{"anonymous", "active", "suspended", "closed"},
	) {
		t.Fatalf("AccountState values = %v", accountState.Values)
	}
	for _, definition := range contractGraph.Governance.Enums {
		if definition.Name == "UserStatus" {
			t.Fatalf("retired UserStatus enum returned from %s", definition.SourcePath)
		}
	}
}

func requireObjectGovernance(
	t *testing.T,
	objects []ast.ObjectGovernance,
	objectID string,
) ast.ObjectGovernance {
	t.Helper()
	for _, object := range objects {
		if object.ObjectID == objectID {
			return object
		}
	}
	t.Fatalf("ContractGraph governance object %q not found", objectID)
	return ast.ObjectGovernance{}
}

func requireEnum(
	t *testing.T,
	definitions []ast.EnumDefinition,
	name string,
) ast.EnumDefinition {
	t.Helper()
	for _, definition := range definitions {
		if definition.Name == name {
			return definition
		}
	}
	t.Fatalf("ContractGraph enum %q not found", name)
	return ast.EnumDefinition{}
}

func requirePrivacyAppLogPolicy(
	t *testing.T,
	policies []ast.PrivacyAppLogPolicy,
	field string,
) ast.PrivacyAppLogPolicy {
	t.Helper()
	for _, policy := range policies {
		if policy.Field == field {
			return policy
		}
	}
	t.Fatalf("privacy app-log policy does not bind canonical field %q", field)
	return ast.PrivacyAppLogPolicy{}
}

func requirePrivacyDeletionCascade(
	t *testing.T,
	cascades []ast.PrivacyDeletionCascade,
	objectID string,
) ast.PrivacyDeletionCascade {
	t.Helper()
	for _, cascade := range cascades {
		if cascade.ObjectID == objectID {
			return cascade
		}
	}
	t.Fatalf("privacy deletion cascade does not bind canonical object %q", objectID)
	return ast.PrivacyDeletionCascade{}
}
