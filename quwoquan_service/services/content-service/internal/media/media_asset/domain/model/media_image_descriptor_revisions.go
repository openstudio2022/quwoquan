package model

import (
	"fmt"
	"strings"
	"time"
)

func (a *MediaAsset) ActiveImageDescriptorRevision() int {
	if a == nil {
		return 0
	}
	return a.activeImageDescriptorRevision
}

func (a *MediaAsset) ImageDescriptorRevisions() []ImageDescriptorRevision {
	if a == nil {
		return nil
	}
	return cloneImageDescriptorRevisions(a.imageDescriptorRevisions)
}

func (a *MediaAsset) ImageDescriptorActivationForRun(
	runID string,
) (ImageDescriptorRevision, bool) {
	if a == nil || strings.TrimSpace(runID) == "" {
		return ImageDescriptorRevision{}, false
	}
	for index := len(a.imageDescriptorRevisions) - 1; index >= 0; index-- {
		revision := a.imageDescriptorRevisions[index]
		if revision.ActivatedByRunID == strings.TrimSpace(runID) {
			return revision, true
		}
	}
	return ImageDescriptorRevision{}, false
}

// ActivateReprocessedImageDescriptor installs a verified new descriptor. The
// caller owns the MediaAsset expected-version CAS; this method only performs
// aggregate-local validation and the all-or-nothing active-pointer mutation.
func (a *MediaAsset) ActivateReprocessedImageDescriptor(
	runID string,
	descriptor ImageProcessingDescriptor,
	now time.Time,
) (previousRevision int, activatedRevision int, err error) {
	if a == nil || a.mediaType != "image" || a.processingStatus != ProcessingStatusReady {
		return 0, 0, fmt.Errorf(
			"%w: descriptor reprocess requires a ready image asset",
			ErrInvalidMediaAssetTransition,
		)
	}
	if strings.TrimSpace(runID) == "" {
		return 0, 0, fmt.Errorf("%w: descriptor reprocess run id is required", ErrInvalidMediaAsset)
	}
	if len(a.imageDescriptorRevisions) == 0 ||
		a.activeImageDescriptorRevision <= 0 ||
		len(a.imageDescriptorRevisions) >= 32 {
		return 0, 0, fmt.Errorf("%w: image descriptor revision state is invalid", ErrInvalidMediaAsset)
	}
	if err := a.validateProcessingDescriptor(
		ProcessingStatusReady,
		MediaProcessingDescriptor{Image: descriptor},
		a.version+1,
	); err != nil {
		return 0, 0, err
	}
	previousIndex := a.imageDescriptorRevisionIndex(a.activeImageDescriptorRevision)
	if previousIndex < 0 {
		return 0, 0, fmt.Errorf("%w: active image descriptor revision is missing", ErrInvalidMediaAsset)
	}
	previousRevision = a.activeImageDescriptorRevision
	if err := a.advance(now); err != nil {
		return 0, 0, err
	}
	cleanupAt := a.updatedAt
	a.imageDescriptorRevisions[previousIndex].CleanupCandidateAt = &cleanupAt
	activatedRevision = a.nextImageDescriptorRevision()
	a.applyImageDescriptor(descriptor)
	a.processingVersion = a.version
	a.imageDescriptorRevisions = append(a.imageDescriptorRevisions, ImageDescriptorRevision{
		Revision:          activatedRevision,
		PreviousRevision:  previousRevision,
		ProcessingVersion: a.processingVersion,
		Descriptor:        a.ImageProcessingDescriptor(),
		ActivatedByRunID:  strings.TrimSpace(runID),
		ActivatedAt:       a.updatedAt,
	})
	a.activeImageDescriptorRevision = activatedRevision
	return previousRevision, activatedRevision, nil
}

// RollbackImageDescriptorRevision restores a descriptor recorded by this
// aggregate. It refuses to overwrite an active descriptor belonging to another
// run, so a stale rollback cannot undo a later successful reprocess.
func (a *MediaAsset) RollbackImageDescriptorRevision(
	runID string,
	previousRevision int,
	activatedRevision int,
	now time.Time,
) error {
	if a == nil || a.mediaType != "image" || a.processingStatus != ProcessingStatusReady {
		return fmt.Errorf(
			"%w: descriptor rollback requires a ready image asset",
			ErrInvalidMediaAssetTransition,
		)
	}
	if strings.TrimSpace(runID) == "" || previousRevision <= 0 || activatedRevision <= 0 {
		return fmt.Errorf("%w: descriptor rollback identity is invalid", ErrInvalidMediaAsset)
	}
	if a.activeImageDescriptorRevision != activatedRevision {
		return fmt.Errorf("%w: descriptor rollback would overwrite a newer activation", ErrInvalidMediaAssetTransition)
	}
	activeIndex := a.imageDescriptorRevisionIndex(activatedRevision)
	previousIndex := a.imageDescriptorRevisionIndex(previousRevision)
	if activeIndex < 0 || previousIndex < 0 ||
		strings.TrimSpace(a.imageDescriptorRevisions[activeIndex].ActivatedByRunID) != strings.TrimSpace(runID) {
		return fmt.Errorf("%w: descriptor rollback audit does not match", ErrInvalidMediaAssetTransition)
	}
	if err := a.advance(now); err != nil {
		return err
	}
	cleanupAt := a.updatedAt
	a.imageDescriptorRevisions[activeIndex].CleanupCandidateAt = &cleanupAt
	previous := a.imageDescriptorRevisions[previousIndex]
	a.applyImageDescriptor(previous.Descriptor)
	a.processingVersion = previous.ProcessingVersion
	a.activeImageDescriptorRevision = previous.Revision
	return nil
}

func (a *MediaAsset) imageDescriptorRevisionIndex(revision int) int {
	for index, candidate := range a.imageDescriptorRevisions {
		if candidate.Revision == revision {
			return index
		}
	}
	return -1
}

func (a *MediaAsset) nextImageDescriptorRevision() int {
	next := 1
	for _, revision := range a.imageDescriptorRevisions {
		if revision.Revision >= next {
			next = revision.Revision + 1
		}
	}
	return next
}

func (a *MediaAsset) applyImageDescriptor(descriptor ImageProcessingDescriptor) {
	a.processorProfile = strings.TrimSpace(descriptor.ProcessorProfile)
	a.imageWidth = descriptor.ImageWidth
	a.imageHeight = descriptor.ImageHeight
	a.imageDeliveryMimeType = strings.TrimSpace(descriptor.ImageDeliveryMimeType)
	a.imageNormalizedObjectKey = strings.TrimSpace(descriptor.ImageNormalizedObjectKey)
	a.imagePublicSliceKey = strings.TrimSpace(descriptor.ImagePublicSliceKey)
	a.imageDominantColor = strings.TrimSpace(descriptor.ImageDominantColor)
	a.imageLQIP = strings.TrimSpace(descriptor.ImageLQIP)
	a.imageContentProfile = strings.TrimSpace(descriptor.ImageContentProfile)
	a.imageDerivativePolicyVersion = descriptor.DerivativePolicyVersion
}
