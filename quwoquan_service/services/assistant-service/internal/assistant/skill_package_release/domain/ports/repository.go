package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type ReleaseReader interface {
	GetRelease(
		context.Context,
		string,
		string,
	) (model.Release, bool, error)
}

type AssetReader interface {
	ReadAsset(context.Context, string) ([]byte, error)
}

type ReleaseStore interface {
	ReleaseReader
	Stage(
		context.Context,
		string,
		string,
		model.Release,
	) (stored model.Release, replayed bool, err error)
}

type ActivationStore interface {
	GetActivation(
		context.Context,
		string,
	) (model.Activation, bool, error)
	GetCommandResult(
		context.Context,
		string,
		string,
		string,
	) (model.Activation, bool, error)
	CommitActivation(
		context.Context,
		string,
		string,
		int,
		model.Activation,
		string,
	) (stored model.Activation, replayed bool, err error)
}
