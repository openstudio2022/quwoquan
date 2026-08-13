package skillcontext

import (
	"fmt"

	readercontract "quwoquan_service/services/assistant-service/generated/assistant/domain_reader_descriptor"
	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/feedbackcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
)

// RuntimeDescriptors declares the Reader adapters provided by assistant_run.
// The composition root must build one object-owned Catalog from this slice and
// pass that same Catalog to both DomainReaderDescriptor queries and
// NewRuntimeRegistry.
//
// 跨域公开对象 Reader（circle/content/entity/user）由对象契约的
// assistant_access.read.reader 声明经 codegen 派生（reader_descriptors.g.go），
// 此处只保留 assistant_run 自有进程内 seam 的 Reader。
func RuntimeDescriptors() ([]readermodel.Descriptor, error) {
	descriptors := []readermodel.Descriptor{
		runDescriptor(
			"assistant.trigger_envelope",
			"trigger.envelope",
			[]string{"trigger"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityInternal,
			[]readermodel.SurfaceKind{
				readermodel.SurfacePersonal,
				readermodel.SurfaceShared,
			},
		),
		runDescriptor(
			"assistant.run_input",
			"turn.slot",
			[]string{"conversation", "device", "memory", "page", "temporal"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.run_preferences",
			"turn.preferences",
			[]string{"conversation", "memory"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.run_feedback_context",
			feedbackcontext.ResolverRef,
			[]string{"memory"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"assistant.skill_subscription_plan",
			"subscription.plan",
			[]string{"domain"},
			generated.AssistantContextAuthorityUserDeclared,
			generated.AssistantContextSensitivityPrivate,
			[]readermodel.SurfaceKind{readermodel.SurfacePersonal},
		),
		runDescriptor(
			"chat.conversation_context",
			"conversation.current_context",
			[]string{"conversation"},
			generated.AssistantContextAuthorityDomainCanonical,
			generated.AssistantContextSensitivityInternal,
			[]readermodel.SurfaceKind{
				readermodel.SurfacePersonal,
				readermodel.SurfaceShared,
			},
		),
	}

	// Object-specific owner contracts override the assistant_run defaults by
	// stable resolver identity. Positional overrides would silently reassign a
	// sibling Reader whenever a new descriptor is inserted.
	for index := range descriptors {
		switch descriptors[index].ResolverRef {
		case "trigger.envelope":
			descriptors[index].MaxFreshnessSeconds = 60 * 60
		case "subscription.plan":
			descriptors[index].OwnerOperationRefs = []string{
				"assistant.skill_subscription.GetSkillSubscription",
			}
			descriptors[index].ObjectTypeRefs = []string{"assistant.SkillSubscription"}
		case "conversation.current_context":
			descriptors[index].MaxFreshnessSeconds = 15 * 60
			descriptors[index].OwnerOperationRefs = []string{
				"assistant.assistant_run.GetAssistantRun",
			}
			descriptors[index].ObjectTypeRefs = []string{"chat.Conversation", "chat.Message"}
		}
	}

	descriptors = append(descriptors, contractDescriptors()...)

	result := make([]readermodel.Descriptor, 0, len(descriptors))
	for _, value := range descriptors {
		descriptor, err := readermodel.NewDescriptor(value)
		if err != nil {
			return nil, fmt.Errorf(
				"invalid context reader descriptor %q: %w",
				value.ResolverRef,
				err,
			)
		}
		result = append(result, descriptor)
	}
	return result, nil
}

// contractDescriptors maps the codegen catalogue derived from object contract
// `assistant_access.read.reader` declarations into the Reader domain model.
func contractDescriptors() []readermodel.Descriptor {
	entries := readercontract.ContractReaderDescriptors()
	descriptors := make([]readermodel.Descriptor, 0, len(entries))
	for _, entry := range entries {
		surfaces := make([]readermodel.SurfaceKind, 0, len(entry.SurfaceKinds))
		for _, surface := range entry.SurfaceKinds {
			surfaces = append(surfaces, readermodel.SurfaceKind(surface))
		}
		descriptors = append(descriptors, readermodel.Descriptor{
			DescriptorID:        entry.DescriptorID,
			ResolverRef:         entry.ResolverRef,
			OwnerService:        entry.OwnerService,
			OwnerOperationRefs:  []string{entry.OwnerOperationRef},
			InputSchemaRef:      entry.InputSchemaRef,
			OutputSchemaRef:     entry.OutputSchemaRef,
			ObjectTypeRefs:      []string{entry.ObjectTypeRef},
			AcceptedSourceKinds: append([]string(nil), entry.AcceptedSourceKinds...),
			Authority:           generated.AssistantContextAuthority(entry.Authority),
			Sensitivity:         generated.AssistantContextSensitivity(entry.Sensitivity),
			MaxFreshnessSeconds: entry.MaxFreshnessSeconds,
			CacheTTLSeconds:     entry.CacheTTLSeconds,
			SurfaceKinds:        surfaces,
			ArtifactPolicy:      readermodel.ArtifactPolicy(entry.ArtifactPolicy),
			CitationPolicy:      readermodel.CitationPolicy(entry.CitationPolicy),
		})
	}
	return descriptors
}

func runDescriptor(
	descriptorID string,
	resolverRef string,
	sourceKinds []string,
	authority generated.AssistantContextAuthority,
	sensitivity generated.AssistantContextSensitivity,
	surfaces []readermodel.SurfaceKind,
) readermodel.Descriptor {
	return readermodel.Descriptor{
		DescriptorID: descriptorID, ResolverRef: resolverRef,
		OwnerService: "assistant-service",
		OwnerOperationRefs: []string{
			"assistant.assistant_run.GetAssistantRun",
		},
		InputSchemaRef:      "assistant.GetAssistantRunQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"assistant.AssistantRun"},
		AcceptedSourceKinds: sourceKinds,
		Authority:           authority,
		Sensitivity:         sensitivity,
		SurfaceKinds:        surfaces,
		ArtifactPolicy:      readermodel.ArtifactInlineBounded,
		CitationPolicy:      readermodel.CitationSourceReference,
	}
}
