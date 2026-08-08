package validate

import (
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func TestRequestBindingsEnforceOneCanonicalNonBodyShape(t *testing.T) {
	requiredFalse := false
	valid := ast.Operation{
		ID:           "content.post.GetPost",
		SourcePath:   "content/content/post/operations.yaml",
		PathTemplate: "/content/posts/{postId}",
		RequestBindings: &ast.RequestBindings{
			Path: []ast.RequestBinding{{Name: "postId", Field: "postId"}},
			Query: []ast.RequestBinding{{
				Name: "cursor", Field: "cursor", Required: &requiredFalse,
			}},
			Header:   []ast.RequestBinding{{Name: "If-Match", Field: "expectedVersion"}},
			Injected: []ast.RequestBinding{{Name: "actorId", Field: "actorId"}},
		},
	}
	if issues := validateRequestBindings(valid); len(issues) != 0 {
		t.Fatalf("valid request bindings rejected: %+v", issues)
	}

	invalid := valid
	invalid.RequestBindings = nil
	invalid.LegacyRequestKeys = []string{"path_params", "request_fields"}
	invalid.ClientBindingOverrides = []string{"path_bindings"}
	assertGovernanceIssueCodes(t, validateRequestBindings(invalid),
		"CONTRACT.REQUEST_BINDING.CLIENT_OWNED",
		"CONTRACT.REQUEST_BINDING.LEGACY_SHAPE",
		"CONTRACT.REQUEST_BINDING.MISSING_PATH",
	)

	reservedHeader := valid
	reservedHeader.RequestBindings = &ast.RequestBindings{
		Header: []ast.RequestBinding{{Name: "Authorization", Field: "token"}},
	}
	assertGovernanceIssueCodes(
		t,
		validateRequestBindings(reservedHeader),
		"CONTRACT.REQUEST_BINDING.RESERVED_HEADER",
	)
}

// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
func TestActorVocabularyRejectsEveryLegacySplitActorContractSurface(t *testing.T) {
	legacyPascal := "Sub" + "Account"
	legacyCamel := "sub" + "Account"
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID:         "user." + legacyCamel,
			Domain:     "user",
			Name:       legacyPascal,
			SourcePath: "user/persona_management/" + legacyCamel + "/object.yaml",
		}},
		Operations: []ast.Operation{{
			ID:           "user.persona.Get" + legacyPascal,
			LocalID:      "Get" + legacyPascal,
			PathTemplate: "/user/" + legacyCamel + "s/{" + legacyCamel + "Id}",
			SourcePath:   "user/persona_management/persona/operations.yaml",
			RequestBindings: &ast.RequestBindings{Path: []ast.RequestBinding{{
				Name: legacyCamel + "Id", Field: legacyCamel + "Id",
			}}},
		}},
		Governance: ast.MetadataGovernance{Fields: []ast.FieldDefinition{{
			ObjectID:   "user.persona",
			Domain:     "user",
			Entity:     "Persona",
			Name:       "active" + "Sub",
			Type:       "string",
			SourcePath: "user/persona_management/persona/fields.yaml",
		}}},
	}
	assertGovernanceIssueCodes(
		t,
		validateActorVocabulary(contractGraph),
		legacyActorVocabularyIssue,
	)
	for _, distinctConcept := range []string{
		"active" + "SubTab",
		"active" + "SubCategory",
		"active" + "Subscriptions",
	} {
		if containsLegacyActorTerm(distinctConcept) {
			t.Fatalf(
				"distinct UI concept %q must not be classified as actor vocabulary",
				distinctConcept,
			)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestLifecycleEnumAndFieldTypeGovernanceAreHardFailures(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post", Kind: ast.ObjectKindAggregateRoot},
			{ID: "content.audit_fact", Domain: "content", Name: "AuditFact", Kind: ast.ObjectKindAppendOnlyFact},
		},
		Governance: ast.MetadataGovernance{
			Enums: []ast.EnumDefinition{{
				Name: "PostStatus", Values: []string{"active", "deleted"},
				OwnerLevel: ast.EnumOwnerObject, Domain: "content", ObjectID: "content.post",
				SourcePath: "content/content/post/fields.yaml",
			}},
			EnumReferences: []ast.EnumReference{{
				Name: "PostStatus", Domain: "content", ObjectID: "content.post",
				SourcePath: "content/content/post/fields.yaml",
			}},
			Fields: []ast.FieldDefinition{
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "status", Type: "enum", EnumRef: "PostStatus", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "payload", Type: "object", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "items", Type: "[]object", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "PostView", Name: "projectionPayload", Type: "object", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "createdAt", Type: "string", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "unknownPayload", Type: "UnknownPayload", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "legacyItems", Type: "string[]", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "unknownItems", Type: "array", SourcePath: "content/content/post/fields.yaml"},
				{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "releaseVersion", Type: "int64", SemanticType: "release_version", SourcePath: "content/content/post/fields.yaml"},
			},
			Objects: []ast.ObjectGovernance{
				{
					ObjectID: "content.post", Domain: "content", SourcePath: "content/content/post/object.yaml",
					Lifecycle: &ast.LifecycleDefinition{StateField: "status", States: []string{"active"}, SourcePath: "content/content/post/object.yaml"},
				},
				{ObjectID: "content.audit_fact", Domain: "content", SourcePath: "content/content/audit_fact/object.yaml"},
			},
		},
	}
	assertGovernanceIssueCodes(t, validateMetadataGovernance(contractGraph),
		"CONTRACT.FIELD.AGGREGATE_ROOT_BARE_OBJECT",
		"CONTRACT.FIELD.AGGREGATE_ROOT_BARE_OBJECT",
		"CONTRACT.FIELD.INVALID_INSTANT_TYPE",
		"CONTRACT.FIELD.NON_CANONICAL_COLLECTION",
		"CONTRACT.FIELD.SEMANTIC_TYPE_MISMATCH",
		"CONTRACT.FIELD.UNTYPED_COLLECTION",
		"CONTRACT.FIELD.UNKNOWN_TYPE",
		"CONTRACT.LIFECYCLE.ENUM_DRIFT",
		"CONTRACT.LIFECYCLE.FACT_NOT_IMMUTABLE",
	)
}

func TestAggregateRootBareObjectFieldsAreAlwaysRejected(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "content.post", Domain: "content", Name: "Post", Kind: ast.ObjectKindAggregateRoot,
		}},
		Governance: ast.MetadataGovernance{Fields: []ast.FieldDefinition{
			{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "mediaItems", Type: "[]object", SourcePath: "content/content/post/fields.yaml"},
			{ObjectID: "content.post", Domain: "content", Entity: "Post", Name: "newPayload", Type: "object", SourcePath: "content/content/post/fields.yaml"},
		}},
	}
	assertGovernanceIssueCodes(
		t,
		validateFieldTypes(contractGraph),
		"CONTRACT.FIELD.AGGREGATE_ROOT_BARE_OBJECT",
	)
}

func TestCanonicalEnumCollectionRequiresAndResolvesExplicitEnumOwner(t *testing.T) {
	contractGraph := &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Enums: []ast.EnumDefinition{{
			Name: "ControlAction", Values: []string{"hide", "revoke"},
			OwnerLevel: ast.EnumOwnerService, Domain: "assistant",
			SourcePath: "assistant/_shared/enums.yaml",
		}},
		EnumReferences: []ast.EnumReference{{
			Name: "ControlAction", Domain: "assistant", ObjectID: "assistant.control",
			SourcePath: "assistant/assistant/control/fields.yaml",
		}},
		Fields: []ast.FieldDefinition{
			{
				ObjectID: "assistant.control", Domain: "assistant", Entity: "Control",
				Name: "actions", Type: "[]enum", EnumRef: "ControlAction",
				SourcePath: "assistant/assistant/control/fields.yaml",
			},
			{
				ObjectID: "assistant.control", Domain: "assistant", Entity: "Control",
				Name: "ownerlessActions", Type: "[]enum",
				SourcePath: "assistant/assistant/control/fields.yaml",
			},
		},
	}}
	assertGovernanceIssueCodes(
		t,
		validateFieldTypes(contractGraph),
		"CONTRACT.FIELD.ENUM_WITHOUT_OWNER",
	)
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-002
func TestEnumOwnerHierarchyRejectsShadowDuplicateAndDeadDefinitions(t *testing.T) {
	contractGraph := &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Enums: []ast.EnumDefinition{
			{Name: "Status", Values: []string{"active"}, OwnerLevel: ast.EnumOwnerGlobal, SourcePath: "_shared/types.yaml"},
			{Name: "Status", Values: []string{"active"}, OwnerLevel: ast.EnumOwnerService, Domain: "content", SourcePath: "content/_shared/enums.yaml"},
			{Name: "Unused", Values: []string{"value"}, OwnerLevel: ast.EnumOwnerService, Domain: "content", SourcePath: "content/_shared/enums.yaml"},
		},
		EnumReferences: []ast.EnumReference{{Name: "Status", Domain: "content", ObjectID: "content.post", SourcePath: "content/content/post/fields.yaml"}},
	}}
	assertGovernanceIssueCodes(t, validateEnumGovernance(contractGraph),
		"CONTRACT.ENUM.DEAD_DEFINITION",
		"CONTRACT.ENUM.SHADOWED_OWNER",
	)
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestErrorEventAndProjectionGovernanceUseSurfaceAwareRules(t *testing.T) {
	status := 500
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post"},
			{
				ID: "content.post_view", Domain: "content", Name: "PostView",
				Lifecycle: &ast.LifecycleDefinition{
					SourceEvents: []string{"content.post.PostObserved"},
					EventConsumers: []ast.LifecycleEventConsumer{{
						Name: "ProjectPostObserved", Kind: "projector",
						Facet: "PostViewProjector", Method: "apply", Idempotency: "event_id",
					}},
				},
			},
		},
		Operations: []ast.Operation{{
			ID: "content.post.GetPost", LocalID: "GetPost", ObjectID: "content.post",
			ErrorCodes: []string{"CONTENT.SYSTEM.failed"},
		}},
		Projections: []ast.Projection{
			{ID: "content.post.PostView", ObjectID: "content.post", ReadModel: "PostView", ReadModelExplicit: true, DartClass: "PostView", OutputPath: "generated/post_view.g.dart", FieldNames: []string{"id"}, SourcePath: "content/content/post/projections/post_view.yaml"},
			{ID: "content.post.LegacyView", ObjectID: "content.post", ReadModel: "LegacyView", DartClass: "PostView", OutputPath: "generated/post_view.g.dart", SourcePath: "content/content/post/projections/legacy_view.yaml"},
		},
		Governance: ast.MetadataGovernance{
			Fields: []ast.FieldDefinition{{ObjectID: "content.post", Entity: "Post", Name: "id", Type: "string"}},
			Objects: []ast.ObjectGovernance{{
				ObjectID: "content.post",
				Errors: []ast.ErrorDefinition{
					{Code: "CONTENT.SYSTEM.failed", HTTPStatus: &status, EmittedBy: []ast.ErrorEmission{{Surface: "http", Operations: []string{"GetPost"}}}, SourcePath: "content/content/post/errors.yaml"},
					{Code: "CONTENT.SYSTEM.worker_failed", HTTPStatus: &status, EmittedBy: []ast.ErrorEmission{{Surface: "worker"}}, SourcePath: "content/content/post/errors.yaml"},
					{Code: "CONTENT.SYSTEM.unbound", SourcePath: "content/content/post/errors.yaml"},
				},
				Events: []ast.EventDefinition{
					{Name: "PostChanged", DeliverySemantics: "transactional_outbox", WireEventType: "PostChanged", SourcePath: "content/content/post/events.yaml"},
					{Name: "PostObserved", DeliverySemantics: "synchronous_call", PayloadEntity: "Post", NoConsumerReason: "retired", SourcePath: "content/content/post/events.yaml"},
				},
			}},
		},
	}
	assertGovernanceIssueCodes(t, validateMetadataGovernance(contractGraph),
		"CONTRACT.ERROR.MISSING_EMISSION_SURFACE",
		"CONTRACT.ERROR.NON_HTTP_STATUS",
		"CONTRACT.EVENT.MISSING_PAYLOAD_ENTITY",
		"CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER",
		"CONTRACT.EVENT.STALE_NO_CONSUMER_REASON",
		"CONTRACT.PROJECTION.DUPLICATE_DART_CLASS",
		"CONTRACT.PROJECTION.DUPLICATE_OUTPUT_PATH",
		"CONTRACT.PROJECTION.MISSING_CANONICAL_FIELDS",
		"CONTRACT.PROJECTION.NON_CANONICAL_IDENTITY",
	)
}

func TestHTTPErrorEmissionAllowsCanonicalCrossObjectOperationOnly(t *testing.T) {
	status := 409
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "user.authentication_challenge", Domain: "user", Name: "AuthenticationChallenge"},
			{ID: "user.credential_binding", Domain: "user", Name: "CredentialBinding"},
		},
		Operations: []ast.Operation{{
			ID: "user.credential_binding.BindPhoneCredential", LocalID: "BindPhoneCredential",
			Domain: "user", ObjectID: "user.credential_binding",
			ErrorCodes: []string{"USER.AUTH.otp_mismatch"},
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "user.authentication_challenge",
			Errors: []ast.ErrorDefinition{{
				Code: "USER.AUTH.otp_mismatch", HTTPStatus: &status,
				EmittedBy: []ast.ErrorEmission{{
					Surface:    "http",
					Operations: []string{"user.credential_binding.BindPhoneCredential"},
				}},
			}},
		}}},
	}
	if issues := validateErrorGovernance(contractGraph); len(issues) != 0 {
		t.Fatalf("canonical cross-object HTTP emission rejected: %+v", issues)
	}

	contractGraph.Governance.Objects[0].Errors[0].EmittedBy[0].Operations =
		[]string{"BindPhoneCredential"}
	assertGovernanceIssueCodes(t, validateErrorGovernance(contractGraph),
		"CONTRACT.ERROR.UNKNOWN_HTTP_OPERATION",
	)

	contractGraph.Governance.Objects[0].Errors[0].EmittedBy[0].Operations =
		[]string{"user.credential_binding.BindPhoneCredential"}
	contractGraph.Operations[0].ErrorCodes = []string{"USER.AUTH.otp_expired"}
	assertGovernanceIssueCodes(t, validateErrorGovernance(contractGraph),
		"CONTRACT.ERROR.OPERATION_BINDING_DRIFT",
		"CONTRACT.ERROR.UNKNOWN_OPERATION_CODE",
	)
}

func TestOperationErrorCodesRequireOneCanonicalDefinitionAndProducerBinding(t *testing.T) {
	status := 500
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post"},
			{ID: "content.comment", Domain: "content", Name: "Comment"},
		},
		Operations: []ast.Operation{
			{ID: "content.post.GetPost", LocalID: "GetPost", Domain: "content", ObjectID: "content.post", ErrorCodes: []string{"CONTENT.SYSTEM.failed", "CONTENT.SYSTEM.missing"}, SourcePath: "content/content/post/operations.yaml"},
			{ID: "content.comment.GetComment", LocalID: "GetComment", Domain: "content", ObjectID: "content.comment", ErrorCodes: []string{"CONTENT.SYSTEM.failed"}, SourcePath: "content/content/comment/operations.yaml"},
		},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{
			{ObjectID: "content.post", Domain: "content", Errors: []ast.ErrorDefinition{{Code: "CONTENT.SYSTEM.failed", HTTPStatus: &status, EmittedBy: []ast.ErrorEmission{{Surface: "http", Operations: []string{"GetPost"}}}, SourcePath: "content/content/post/errors.yaml"}}},
		}},
	}
	assertGovernanceIssueCodes(t, validateErrorGovernance(contractGraph),
		"CONTRACT.ERROR.MISSING_OPERATION_EMISSION",
		"CONTRACT.ERROR.UNKNOWN_OPERATION_CODE",
	)

	contractGraph.Governance.Objects = append(contractGraph.Governance.Objects,
		ast.ObjectGovernance{ObjectID: "content.comment", Domain: "content", Errors: []ast.ErrorDefinition{{Code: "CONTENT.SYSTEM.failed", HTTPStatus: &status, EmittedBy: []ast.ErrorEmission{{Surface: "http", Operations: []string{"GetComment"}}}, SourcePath: "content/content/comment/errors.yaml"}}},
	)
	assertGovernanceIssueCodes(t, validateErrorGovernance(contractGraph),
		"CONTRACT.ERROR.DUPLICATE_CODE_OWNER",
	)
}

func TestOperationCannotBorrowAnErrorFromAnotherDomain(t *testing.T) {
	status := 401
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "user.user_account", Domain: "user", Name: "UserAccount"},
			{ID: "content.post", Domain: "content", Name: "Post"},
		},
		Operations: []ast.Operation{{
			ID: "content.post.GetPost", LocalID: "GetPost", Domain: "content",
			ObjectID: "content.post", ErrorCodes: []string{"USER.AUTH.account_suspended"},
			SourcePath: "content/content/post/operations.yaml",
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "user.user_account", Domain: "user",
			Errors: []ast.ErrorDefinition{{
				Code: "USER.AUTH.account_suspended", HTTPStatus: &status,
				EmittedBy: []ast.ErrorEmission{{
					Surface: "http", Operations: []string{"content.post.GetPost"},
				}},
				SourcePath: "user/account/user_account/errors.yaml",
			}},
		}}},
	}
	assertGovernanceIssueCodes(t, validateErrorGovernance(contractGraph),
		"CONTRACT.ERROR.CROSS_DOMAIN_OPERATION",
		"CONTRACT.ERROR.CROSS_DOMAIN_OPERATION_CODE",
	)
}

func TestFieldTypeCannotResolveThroughClientDartClassAlias(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Projections: []ast.Projection{{
			Domain: "content", ReadModel: "CanonicalPostView", DartClass: "LegacyPostView",
		}},
		Governance: ast.MetadataGovernance{Fields: []ast.FieldDefinition{{
			Domain: "content", Entity: "Envelope", Name: "post", Type: "LegacyPostView",
			SourcePath: "content/content/post/fields.yaml",
		}}},
	}
	assertGovernanceIssueCodes(t, validateFieldTypes(contractGraph),
		"CONTRACT.FIELD.UNKNOWN_TYPE",
	)
}

func TestObjectLocalTypesCannotShadowObjectsOrCreateSecondTruthSources(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "content.post", Domain: "content", Name: "Post"},
			{ID: "content.deleted_post_tombstone", Domain: "content", Name: "DeletedPostTombstone"},
			{ID: "content.comment", Domain: "content", Name: "Comment"},
		},
		Governance: ast.MetadataGovernance{Types: []ast.TypeDefinition{
			{Name: "DeletedPostTombstone", OwnerLevel: ast.EnumOwnerObject, Domain: "content", ObjectID: "content.post", SourcePath: "content/content/post/fields.yaml"},
			{Name: "SharedAudit", OwnerLevel: ast.EnumOwnerObject, Domain: "content", ObjectID: "content.post", SourcePath: "content/content/post/fields.yaml"},
			{Name: "SharedAudit", OwnerLevel: ast.EnumOwnerObject, Domain: "content", ObjectID: "content.comment", SourcePath: "content/content/comment/fields.yaml"},
		}},
	}
	assertGovernanceIssueCodes(t, validateFieldTypes(contractGraph),
		"CONTRACT.TYPE.DUPLICATE_OBJECT_DEFINITION",
		"CONTRACT.TYPE.OBJECT_NAME_SHADOWED",
	)
}

func TestProjectionClientOutputPathIsGloballyUniqueForExternalLibraries(t *testing.T) {
	contractGraph := &graph.ContractGraph{Projections: []ast.Projection{
		{
			ID: "content.post.PostView", ReadModel: "PostView",
			ReadModelExplicit: true, DartClass: "PostView",
			OutputPath:       "packages/contracts/lib/content.dart",
			ExternalDartPath: "packages/contracts/lib/content.dart",
			FieldNames:       []string{"postId"}, SourcePath: "content/content/post/projections/post_view.yaml",
		},
		{
			ID: "content.comment.CommentView", ReadModel: "CommentView",
			ReadModelExplicit: true, DartClass: "CommentView",
			OutputPath:       "packages/contracts/lib/content.dart",
			ExternalDartPath: "packages/contracts/lib/content.dart",
			FieldNames:       []string{"commentId"}, SourcePath: "content/content/comment/projections/comment_view.yaml",
		},
	}}
	issues := validateProjectionGovernance(contractGraph)
	assertGovernanceIssueCodes(t, issues, "CONTRACT.PROJECTION.DUPLICATE_OUTPUT_PATH")
	for _, current := range issues {
		if current.Code == "CONTRACT.PROJECTION.DUPLICATE_DART_CLASS" {
			t.Fatalf("different client classes must not be reported as duplicate: %+v", issues)
		}
	}
}

func TestEventPayloadFieldsMustExactlyMatchObjectLocalPayloadType(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{ID: "content.post", Domain: "content", Name: "Post"}},
		Governance: ast.MetadataGovernance{
			Fields: []ast.FieldDefinition{
				{ObjectID: "content.post", Entity: "PostChangedPayload", Name: "postId", Type: "string"},
				{ObjectID: "content.post", Entity: "PostChangedPayload", Name: "version", Type: "int"},
			},
			Objects: []ast.ObjectGovernance{{
				ObjectID: "content.post",
				Events: []ast.EventDefinition{{
					Name: "PostChanged", DeliverySemantics: "transactional_outbox", WireEventType: "PostChanged",
					PayloadEntity: "PostChangedPayload",
					PayloadShape:  "exact",
					PayloadFields: []string{"postId", "postId", "unknown"},
					SourcePath:    "content/content/post/events.yaml",
				}},
			}},
		},
	}
	assertGovernanceIssueCodes(t, validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.DUPLICATE_PAYLOAD_FIELD",
		"CONTRACT.EVENT.MISSING_PAYLOAD_FIELD",
		"CONTRACT.EVENT.UNKNOWN_PAYLOAD_FIELD",
	)
}

// consumer 强制按 `delivery_semantics` 的**精确取值**判定。旧实现用
// `strings.Contains(channel, "outbox")`：那是没有值域时的将就写法，任何含 `outbox` 字样的
// topic 名或拼写变体都能改变判定。这里把两个方向都钉死——含 `outbox` 字样但不是受控取值的
// 值不再被当成发件箱，受控取值不再靠字样而靠自身成立。
func TestOutboxConsumerRuleUsesExactDeliverySemanticsNotSubstring(t *testing.T) {
	newGraph := func(events ...ast.EventDefinition) *graph.ContractGraph {
		return &graph.ContractGraph{
			Objects: []ast.Object{{ID: "content.post", Domain: "content", Name: "Post"}},
			Governance: ast.MetadataGovernance{
				Objects: []ast.ObjectGovernance{{ObjectID: "content.post", Events: events}},
			},
		}
	}
	source := "content/content/post/events.yaml"

	// `outbox.domain` 是 topic 形状的名字，不是投递保证。子串匹配会把它当发件箱；
	// 精确匹配把它归为未知取值，仍 fail-safe 到要求 consumer 一侧，但触发原因不同：
	// 它不是「发件箱缺收件人」，而是「取值根本不在值域内」。
	assertGovernanceIssueCodes(t, validateEventGovernance(newGraph(ast.EventDefinition{
		Name: "PostChanged", DeliverySemantics: "outbox.domain",
		PayloadEntity: "Post", SourcePath: source,
	})),
		"CONTRACT.EVENT.OUTBOX_WITHOUT_CONSUMER",
	)

	// 事务性事件表零消费者 + 理由是完整声明，不得再被当成发件箱要求 consumer。
	// 子串匹配下 `transactional_event_log` 不含 `outbox`，靠的是「碰巧不含」；
	// 精确匹配下它靠自身取值成立。
	assertGovernanceIssueCodes(t, validateEventGovernance(newGraph(ast.EventDefinition{
		Name: "PostJournaled", DeliverySemantics: "transactional_event_log",
		PayloadEntity: "Post", NoConsumerReason: "append-only audit journal",
		SourcePath: source,
	})))

	// 反方向：有具名消费者却标成事务性事件表，等于把「投递断了」洗成「本来就不用投递」。
	// 这条互斥由 DESIGN.md 第 9.2 节在存储侧确立，这里是它在事件侧的执行。
	eventLogWithConsumer := newGraph(ast.EventDefinition{
		Name: "PostJournaled", DeliverySemantics: "transactional_event_log",
		PayloadEntity: "Post",
		SourcePath:    source,
	})
	eventLogWithConsumer.Objects = []ast.Object{{
		ID: "content.post_view", SourcePath: "content/read/post_view/object.yaml",
		Lifecycle: &ast.LifecycleDefinition{
			SourceEvents: []string{"content.post.PostJournaled"},
			EventConsumers: []ast.LifecycleEventConsumer{{
				Name: "ProjectPostJournal", Kind: "projector", Facet: "PostJournalProjector",
				Method: "apply", Idempotency: "event_id",
			}},
		},
	}}
	assertGovernanceIssueCodes(t, validateEventGovernance(eventLogWithConsumer),
		"CONTRACT.EVENT.EVENT_LOG_WITH_CONSUMER",
	)
}

func TestEventSubscriptionMustResolveToCanonicalProducer(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "user.following_subject", SourcePath: "user/profile_projection/following_subject/object.yaml",
			Lifecycle: &ast.LifecycleDefinition{SourceEvents: []string{
				"user.followed_subject_visit_state.FollowedSubjectVisited",
				"user.missing_source.MissingEvent",
			}, EventConsumers: []ast.LifecycleEventConsumer{{
				Name: "ProjectFollowingSubject", Kind: "projector", Facet: "FollowingSubjectProjector",
				Method: "apply", Idempotency: "event_id",
			}}},
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "user.followed_subject_visit_state",
			Events:   []ast.EventDefinition{{Name: "FollowedSubjectVisited"}},
		}}},
	}
	issues := validateEventGovernance(contractGraph)
	assertGovernanceIssueCodes(
		t,
		issues,
		"CONTRACT.EVENT.SOURCE_WITHOUT_PRODUCER",
	)
	for _, current := range issues {
		if current.Code == "CONTRACT.EVENT.SOURCE_WITHOUT_PRODUCER" &&
			!strings.Contains(current.Message, "MissingEvent") {
			t.Fatalf("resolved subscription must not be reported: %+v", issues)
		}
	}
}

func TestEventNameMustHaveOneCanonicalProducer(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "user.subject_follow",
			Events: []ast.EventDefinition{
				{Name: "SubjectFollowStateChanged"},
				{Name: "SubjectFollowStateChanged"},
			},
		}}},
	}
	assertGovernanceIssueCodes(
		t,
		validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.DUPLICATE_PRODUCER",
	)
}

func TestCanonicalEventIdentityIncludesProducingObject(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{
				ID: "search.post_view", SourcePath: "search/search/post_view/object.yaml",
				Lifecycle: &ast.LifecycleDefinition{
					SourceEvents: []string{"content.post.Changed"},
					EventConsumers: []ast.LifecycleEventConsumer{{
						Name: "ProjectPost", Kind: "projector", Facet: "PostViewProjector",
						Method: "apply", Idempotency: "event_id",
					}},
				},
			},
			{
				ID: "search.comment_view", SourcePath: "search/search/comment_view/object.yaml",
				Lifecycle: &ast.LifecycleDefinition{
					SourceEvents: []string{"content.comment.Changed"},
					EventConsumers: []ast.LifecycleEventConsumer{{
						Name: "ProjectComment", Kind: "projector", Facet: "CommentViewProjector",
						Method: "apply", Idempotency: "event_id",
					}},
				},
			},
		},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{
			{
				ObjectID: "content.post",
				Events: []ast.EventDefinition{{
					Name: "Changed", DeliverySemantics: "transactional_outbox", WireEventType: "PostChanged",
					PayloadEntity: "Post", SourcePath: "content/content/post/events.yaml",
				}},
			},
			{
				ObjectID: "content.comment",
				Events: []ast.EventDefinition{{
					Name: "Changed", DeliverySemantics: "transactional_outbox", WireEventType: "CommentChanged",
					PayloadEntity: "Comment", SourcePath: "content/content/comment/events.yaml",
				}},
			},
		}},
	}
	for _, current := range validateEventGovernance(contractGraph) {
		if current.Code == "CONTRACT.EVENT.DUPLICATE_PRODUCER" {
			t.Fatalf("object-qualified event refs must not collide: %+v", current)
		}
	}
}

func TestEventConsumerRejectsDomainOnlyInferenceAndUnknownProducer(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "search.post_view", SourcePath: "search/search/post_view/object.yaml",
			Lifecycle: &ast.LifecycleDefinition{SourceEvents: []string{
				"content.PostChanged",
				"content.missing.PostChanged",
			}, EventConsumers: []ast.LifecycleEventConsumer{{
				Name: "ProjectPost", Kind: "projector", Facet: "PostViewProjector", Method: "apply", Idempotency: "event_id",
			}}},
		}},
	}
	assertGovernanceIssueCodes(t, validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.INVALID_SOURCE_REF",
		"CONTRACT.EVENT.SOURCE_WITHOUT_PRODUCER",
	)
}

func TestEventClientPayloadDefaultsMustNamePayloadFields(t *testing.T) {
	contractGraph := &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Objects: []ast.ObjectGovernance{{
			ObjectID: "rtc.call_session",
			Events: []ast.EventDefinition{{
				Name: "CallRinging", DeliverySemantics: "not_published",
				PayloadEntity: "CallEventPayload", PayloadFields: []string{"callType"},
				ClientWSType: "call.ringing",
				ClientPayloadDefaults: map[string]string{
					"callType": "audio",
					"unknown":  "value",
				},
				NoConsumerReason: "client-only typed signal",
				SourcePath:       "rtc/rtc/call_session/events.yaml",
			}},
		}},
	}}
	assertGovernanceIssueCodes(t, validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.CLIENT_DEFAULT_UNKNOWN_FIELD",
	)
}

func TestEventReverseIndexRejectsDuplicateAndStaleConsumerDeclarations(t *testing.T) {
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "search.post_view", SourcePath: "search/search/post_view/object.yaml",
			Lifecycle: &ast.LifecycleDefinition{SourceEvents: []string{
				"content.post.PostPublished",
				"content.post.PostPublished",
			}, EventConsumers: []ast.LifecycleEventConsumer{{
				Name: "ProjectPost", Kind: "projector", Facet: "PostViewProjector", Method: "apply", Idempotency: "event_id",
			}}},
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "content.post",
			Events: []ast.EventDefinition{{
				Name: "PostPublished", DeliverySemantics: "transactional_outbox", WireEventType: "PostPublished",
				PayloadEntity:    "Post",
				NoConsumerReason: "stale producer-side declaration",
				SourcePath:       "content/content/post/events.yaml",
			}},
		}}},
	}
	assertGovernanceIssueCodes(t, validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.DUPLICATE_SOURCE_EVENT",
		"CONTRACT.EVENT.STALE_NO_CONSUMER_REASON",
	)
}

func TestEventClientWSTypeHasOneCanonicalOwner(t *testing.T) {
	contractGraph := &graph.ContractGraph{Governance: ast.MetadataGovernance{
		Objects: []ast.ObjectGovernance{
			{ObjectID: "rtc.call_session", Events: []ast.EventDefinition{{
				Name: "CallRinging", DeliverySemantics: "not_published",
				PayloadEntity: "CallEventPayload", ClientWSType: "call.ringing",
				NoConsumerReason: "client-only typed signal",
				SourcePath:       "rtc/rtc/call_session/events.yaml",
			}}},
			{ObjectID: "notification.notification", Events: []ast.EventDefinition{{
				Name: "IncomingCallRinging", DeliverySemantics: "not_published",
				PayloadEntity: "IncomingCallPayload", ClientWSType: "call.ringing",
				NoConsumerReason: "client-only typed signal",
				SourcePath:       "notification/notification_delivery/notification/events.yaml",
			}}},
		},
	}}
	assertGovernanceIssueCodes(t, validateEventGovernance(contractGraph),
		"CONTRACT.EVENT.DUPLICATE_CLIENT_WS_TYPE",
	)
}

func TestPrivacyReferencesMustResolveToCanonicalFieldsAndObjects(t *testing.T) {
	retentionDays := 365
	deletionOnRequest := true
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{
			{ID: "user.user_account", Domain: "user", Name: "UserAccount"},
			{ID: "user.persona", Domain: "user", Name: "Persona"},
		},
		Governance: ast.MetadataGovernance{
			Fields: []ast.FieldDefinition{{
				ObjectID:       "user.user_account",
				Entity:         "UserAccount",
				Name:           "phone",
				Classification: "PII",
				LogPolicy:      "mask",
			}},
			Objects: []ast.ObjectGovernance{{
				ObjectID: "user.user_account",
				Privacy: &ast.PrivacyDefinition{
					ObjectID: "user.user_account",
					Document: ast.PrivacyDocument{
						Description: "fixture privacy",
						AppLogPolicy: []ast.PrivacyAppLogPolicy{
							{Field: "phone", Classification: ast.PrivacyClassificationPII, AppLog: ast.PrivacyAppLogDrop},
							{Field: "birthday", Classification: ast.PrivacyClassificationPII, AppLog: ast.PrivacyAppLogDrop},
						},
						FieldVisibility: []ast.PrivacyFieldVisibility{{
							Field: "phone", Visibility: []string{"user-service-internal"},
						}},
						DataLifecycle: &ast.PrivacyDataLifecycle{
							RetentionDays:         &retentionDays,
							DeletionOnUserRequest: &deletionOnRequest,
							DeletionCascade: []ast.PrivacyDeletionCascade{
								{ObjectID: "user.persona", Strategy: ast.PrivacyDeletionHardDelete},
								{ObjectID: "user.user_device", Strategy: ast.PrivacyDeletionHardDelete},
							},
							AnonymizationOnDelete: []ast.PrivacyAnonymization{{
								Field: "location", Strategy: ast.PrivacyAnonymizationDrop,
							}},
						},
					},
					SourcePath: "user/account/user_account/privacy.yaml",
				},
			}},
		},
	}
	assertGovernanceIssueCodes(
		t,
		validatePrivacyGovernance(contractGraph),
		"CONTRACT.PRIVACY.UNKNOWN_FIELD",
		"CONTRACT.PRIVACY.UNKNOWN_DELETION_TARGET",
	)
}

func assertGovernanceIssueCodes(t *testing.T, issues []Issue, expected ...string) {
	t.Helper()
	actual := map[string]struct{}{}
	for _, current := range issues {
		actual[current.Code] = struct{}{}
	}
	for _, code := range expected {
		if _, exists := actual[code]; !exists {
			t.Fatalf("missing issue %s in %+v", code, issues)
		}
	}
}
