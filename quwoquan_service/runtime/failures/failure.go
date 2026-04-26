package failures

import "strings"

type Origin string
type Kind string
type Nature string

const (
	OriginUser             Origin = "user"
	OriginEnvironment      Origin = "environment"
	OriginLocalClient      Origin = "localClient"
	OriginRemoteDependency Origin = "remoteDependency"
	OriginSystem           Origin = "system"
	OriginDeveloper        Origin = "developer"
)

const (
	KindValidation  Kind = "validation"
	KindContract    Kind = "contract"
	KindPermission  Kind = "permission"
	KindAuth        Kind = "auth"
	KindNetwork     Kind = "network"
	KindRateLimited Kind = "rateLimited"
	KindUnavailable Kind = "unavailable"
	KindTimeout     Kind = "timeout"
	KindNotFound    Kind = "notFound"
	KindUnsupported Kind = "unsupported"
	KindCancelled   Kind = "cancelled"
	KindStorage     Kind = "storage"
	KindParsing     Kind = "parsing"
	KindModel       Kind = "model"
	KindInternal    Kind = "internal"
)

const (
	NatureTransient          Nature = "transient"
	NaturePermanent          Nature = "permanent"
	NatureRequiresUserAction Nature = "requiresUserAction"
	NatureRequiresPermission Nature = "requiresPermission"
	NatureBug                Nature = "bug"
)

const UnknownCode = "CLOUD.SYSTEM.unknown_error"

type FailureBase interface {
	RuntimeCode() string
	RuntimeOrigin() Origin
	RuntimeKind() Kind
	RuntimeNature() Nature
	RuntimeLocation() Location
	RuntimeContext() Context
}

type Failure struct {
	Code     string   `json:"code"`
	Origin   Origin   `json:"origin"`
	Kind     Kind     `json:"kind"`
	Nature   Nature   `json:"nature"`
	Location Location `json:"location"`
	Context  Context  `json:"context"`
}

func Unknown() Failure {
	return Failure{
		Code:     UnknownCode,
		Origin:   OriginSystem,
		Kind:     KindInternal,
		Nature:   NatureBug,
		Location: UnknownLocation(),
		Context:  Context{},
	}
}

func (f Failure) Normalized() Failure {
	if strings.TrimSpace(f.Code) == "" {
		f.Code = UnknownCode
	}
	if f.Origin == "" {
		f.Origin = OriginSystem
	}
	if f.Kind == "" {
		f.Kind = KindInternal
	}
	if f.Nature == "" {
		f.Nature = NatureBug
	}
	f.Location = f.Location.Normalized()
	f.Context = f.Context.Normalized()
	return f
}

func (f Failure) RuntimeCode() string {
	return f.Code
}

func (f Failure) RuntimeOrigin() Origin {
	return f.Origin
}

func (f Failure) RuntimeKind() Kind {
	return f.Kind
}

func (f Failure) RuntimeNature() Nature {
	return f.Nature
}

func (f Failure) RuntimeLocation() Location {
	return f.Location
}

func (f Failure) RuntimeContext() Context {
	return f.Context
}
