package codegen

// generatorConfig holds optional generation behavior (defaults match current output).
type generatorConfig struct {
	typedEnums         bool
	resolveSliceEntity bool
	skipViewEntities   bool
	goFieldIDSuffix    bool
}

// GeneratorOption configures [Generator] behavior.
type GeneratorOption func(*generatorConfig)

// WithTypedEnums emits named string enum types and const blocks using values from
// contracts/metadata/_shared/types.yaml (via [registry.EntityRegistry.GetEnum]).
func WithTypedEnums() GeneratorOption {
	return func(c *generatorConfig) {
		c.typedEnums = true
	}
}

// WithSliceEntityRefs resolves field types like "[]CircleSectionConfig" to Go slices
// of structs when the element name matches an entity in the same aggregate.
func WithSliceEntityRefs() GeneratorOption {
	return func(c *generatorConfig) {
		c.resolveSliceEntity = true
	}
}

// WithSkipViewEntities skips entity names with suffix "View" (read/search projections).
func WithSkipViewEntities() GeneratorOption {
	return func(c *generatorConfig) {
		c.skipViewEntities = true
	}
}

// WithGoFieldIDSuffix maps trailing "Id" in JSON field names to a Go name ending in "ID"
// (e.g. ownerId -> OwnerID). Off by default for backward compatibility with older generated models.
func WithGoFieldIDSuffix() GeneratorOption {
	return func(c *generatorConfig) {
		c.goFieldIDSuffix = true
	}
}
