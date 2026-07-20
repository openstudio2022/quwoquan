package processing

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	runtimemedia "quwoquan_service/runtime/media"
	mediaprocessing "quwoquan_service/services/content-service/internal/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/domain/media/model"
)

const ImageProcessorProfile = "content_processing_image_baseline_v1"

func (p *FFmpegMediaProcessor) processImage(
	ctx context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	ctx, cancel := context.WithTimeout(ctx, p.config.JobTimeout)
	defer cancel()

	workDir, err := os.MkdirTemp(p.config.WorkDir, "image-processing-")
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"create image processing work dir: %w",
			err,
		)
	}
	defer os.RemoveAll(workDir)

	sourcePath := filepath.Join(workDir, "source"+sourceExtension(request.ContentType))
	if err := p.downloadObject(ctx, request.SourceObjectKey, sourcePath); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	sourceProbe, err := p.probe(ctx, sourcePath)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if !sourceProbe.HasVideo || sourceProbe.Width <= 0 || sourceProbe.Height <= 0 {
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: "uploaded media has no decodable image frame",
		}
	}
	sourcePixels := int64(sourceProbe.Width) * int64(sourceProbe.Height)
	if sourceProbe.Width > mediamodel.MaxImageDimension ||
		sourceProbe.Height > mediamodel.MaxImageDimension ||
		sourcePixels <= 0 ||
		sourcePixels > mediamodel.MaxImagePixels {
		return mediaprocessing.ProcessOutcome{}, &mediaprocessing.RejectionError{
			Reason: fmt.Sprintf(
				"image dimensions %dx%d exceed the %dpx/%d-pixel ceiling",
				sourceProbe.Width,
				sourceProbe.Height,
				mediamodel.MaxImageDimension,
				mediamodel.MaxImagePixels,
			),
		}
	}

	deliveryContentType, extension := normalizedImageFormat(
		request.ContentType,
		sourceProbe.PixelFormat,
	)
	deliveryPath := filepath.Join(workDir, "delivery"+extension)
	if err := p.normalizeImage(
		ctx,
		sourcePath,
		deliveryPath,
		deliveryContentType,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	deliveryProbe, err := p.probe(ctx, deliveryPath)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if !deliveryProbe.HasVideo ||
		deliveryProbe.Width <= 0 ||
		deliveryProbe.Height <= 0 ||
		deliveryProbe.Width > mediamodel.MaxImageDeliveryDimension ||
		deliveryProbe.Height > mediamodel.MaxImageDeliveryDimension {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"normalized image failed self-check: dimensions=%dx%d",
			deliveryProbe.Width,
			deliveryProbe.Height,
		)
	}

	privateObjectKey := fmt.Sprintf(
		"media/processed/image/%s/v%d/source%s",
		strings.TrimSpace(request.AssetID),
		request.AssetVersion,
		extension,
	)
	publicSliceKey := runtimemedia.BuildContentMediaPublicSliceKey(
		"image",
		request.AssetID,
		request.AssetVersion,
		deliveryContentType,
	)
	if publicSliceKey == "" {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"derive image public slice for asset %q",
			request.AssetID,
		)
	}
	if _, err := p.uploadFile(
		ctx,
		deliveryPath,
		privateObjectKey,
		deliveryContentType,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}

	return mediaprocessing.ProcessOutcome{
		Descriptor: mediamodel.MediaProcessingDescriptor{
			Image: mediamodel.ImageProcessingDescriptor{
				ProcessorProfile:         ImageProcessorProfile,
				ImageWidth:               deliveryProbe.Width,
				ImageHeight:              deliveryProbe.Height,
				ImageDeliveryContentType: deliveryContentType,
				ImageNormalizedObjectKey: privateObjectKey,
				ImagePublicSliceKey:      publicSliceKey,
			},
		},
	}, nil
}

func (p *FFmpegMediaProcessor) normalizeImage(
	ctx context.Context,
	sourcePath string,
	deliveryPath string,
	deliveryContentType string,
) error {
	filter := fmt.Sprintf(
		"scale=w='min(%d,iw)':h='min(%d,ih)':force_original_aspect_ratio=decrease,setsar=1",
		mediamodel.MaxImageDeliveryDimension,
		mediamodel.MaxImageDeliveryDimension,
	)
	args := []string{
		"-hide_banner", "-loglevel", "error", "-y",
		"-i", sourcePath,
		"-map", "0:v:0",
		"-frames:v", "1",
	}
	switch deliveryContentType {
	case "image/png":
		args = append(
			args,
			"-vf", filter+",format=rgba",
			"-c:v", "png",
			"-compression_level", "6",
		)
	default:
		args = append(
			args,
			"-vf", filter+",format=yuvj420p",
			"-q:v", "2",
		)
	}
	args = append(args, deliveryPath)
	if _, err := runCommand(ctx, p.config.FFmpegPath, args...); err != nil {
		if ctx.Err() != nil {
			return fmt.Errorf("image normalization timed out: %w", ctx.Err())
		}
		return &mediaprocessing.RejectionError{
			Reason: fmt.Sprintf(
				"image normalization failed: %v",
				commandFailureSummary(err),
			),
		}
	}
	info, err := os.Stat(deliveryPath)
	if err != nil || info.Size() <= 0 {
		return &mediaprocessing.RejectionError{
			Reason: "image normalization produced no decodable artifact",
		}
	}
	return nil
}

func normalizedImageFormat(contentType string, pixelFormat string) (string, string) {
	contentType = strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0]))
	pixelFormat = strings.ToLower(strings.TrimSpace(pixelFormat))
	if contentType == "image/png" ||
		contentType == "image/gif" ||
		strings.Contains(pixelFormat, "rgba") ||
		strings.Contains(pixelFormat, "bgra") ||
		strings.Contains(pixelFormat, "argb") ||
		strings.Contains(pixelFormat, "yuva") ||
		strings.Contains(pixelFormat, "gbrap") ||
		pixelFormat == "pal8" {
		return "image/png", ".png"
	}
	return "image/jpeg", ".jpg"
}
