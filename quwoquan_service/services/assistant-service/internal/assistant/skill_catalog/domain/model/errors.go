package model

import "errors"

var (
	ErrConfigurationSchemaDigestMismatch = errors.New("Skill configuration schema digest mismatch")
	ErrConfigurationInvalid              = errors.New("Skill configuration does not satisfy its schema")
	ErrSkillNotFound                     = errors.New("Skill is not present in the active package")
	ErrSkillNotShared                    = errors.New("Skill is not eligible for the shared surface")
)
