package processing

import (
	"context"
	"encoding/base64"
	"fmt"
	"image"
	_ "image/jpeg"
	_ "image/png"
	"os"
	"path/filepath"
	"strings"

	runtimemedia "quwoquan_service/runtime/media"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_asset"
	mediaprocessing "quwoquan_service/services/content-service/internal/content/post/application/media/processing"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
)

// ImageProcessorProfile is the stable semantic identity of the sole image
// normalization pipeline. Output bytes retain their own SHA256 identity.
const ImageProcessorProfile = "content_processing_image_baseline"

func (p *FFmpegMediaProcessor) processImage(
	ctx context.Context,
	request mediaprocessing.ProcessRequest,
) (mediaprocessing.ProcessOutcome, error) {
	ctx, cancel := context.WithTimeout(ctx, p.Config.JobTimeout)
	defer cancel()

	workDir, err := p.CreateWorkDir("image-processing-")
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"create image processing work dir: %w",
			err,
		)
	}
	defer os.RemoveAll(workDir)

	sourcePath := filepath.Join(workDir, "source"+sourceExtension(request.MimeType))
	if err := p.downloadObject(ctx, request.SourceObjectKey, sourcePath); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	sourceProbe, err := p.Probe(ctx, sourcePath)
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

	deliveryMimeType, extension := normalizedImageFormat(
		request.MimeType,
		sourceProbe.PixelFormat,
	)
	deliveryPath := filepath.Join(workDir, "delivery"+extension)
	if err := p.normalizeImage(
		ctx,
		sourcePath,
		deliveryPath,
		deliveryMimeType,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	deliveryProbe, err := p.Probe(ctx, deliveryPath)
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
	dominantColor, lqip, contentProfile, err := p.imageDeliveryPresentation(
		ctx,
		deliveryPath,
		workDir,
		deliveryMimeType,
	)
	if err != nil {
		return mediaprocessing.ProcessOutcome{}, err
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
		deliveryMimeType,
	)
	if publicSliceKey == "" {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"derive image public slice for asset %q",
			request.AssetID,
		)
	}
	if _, err := p.UploadFile(
		ctx,
		deliveryPath,
		privateObjectKey,
		deliveryMimeType,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}
	if _, err := p.UploadFile(
		ctx,
		deliveryPath,
		publicSliceKey,
		deliveryMimeType,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, fmt.Errorf(
			"publish image delivery slice: %w",
			err,
		)
	}
	if err := p.verifyImageReadback(
		ctx,
		publicSliceKey,
		filepath.Join(workDir, "public-slice-readback"+extension),
		deliveryProbe.Width,
		deliveryProbe.Height,
	); err != nil {
		return mediaprocessing.ProcessOutcome{}, err
	}

	return mediaprocessing.ProcessOutcome{
		Descriptor: mediamodel.MediaProcessingDescriptor{
			Image: mediamodel.ImageProcessingDescriptor{
				ProcessorProfile:         ImageProcessorProfile,
				ImageWidth:               deliveryProbe.Width,
				ImageHeight:              deliveryProbe.Height,
				ImageDeliveryMimeType:    deliveryMimeType,
				ImageNormalizedObjectKey: privateObjectKey,
				ImagePublicSliceKey:      publicSliceKey,
				ImageDominantColor:       dominantColor,
				ImageLQIP:                lqip,
				ImageContentProfile:      contentProfile,
				DerivativePolicyVersion:  contentgenerated.ContentImageDerivativePolicyVersion,
			},
		},
	}, nil
}

// verifyImageReadback proves that the public delivery identity points at the
// bytes just normalized. A successful private upload alone is insufficient:
// descriptor activation must never make a CDN slice visible before it can be
// fetched and decoded from the object store.
func (p *FFmpegMediaProcessor) verifyImageReadback(
	ctx context.Context,
	publicSliceKey string,
	readbackPath string,
	expectedWidth int,
	expectedHeight int,
) error {
	if err := p.downloadObject(ctx, publicSliceKey, readbackPath); err != nil {
		return fmt.Errorf("read back image public slice %q: %w", publicSliceKey, err)
	}
	probe, err := p.Probe(ctx, readbackPath)
	if err != nil {
		return fmt.Errorf("probe image public slice %q: %w", publicSliceKey, err)
	}
	if !probe.HasVideo || probe.Width != expectedWidth || probe.Height != expectedHeight {
		return fmt.Errorf(
			"image public slice %q readback dimensions=%dx%d, want %dx%d",
			publicSliceKey,
			probe.Width,
			probe.Height,
			expectedWidth,
			expectedHeight,
		)
	}
	return nil
}

func (p *FFmpegMediaProcessor) imageDeliveryPresentation(
	ctx context.Context,
	deliveryPath string,
	workDir string,
	deliveryMimeType string,
) (string, string, string, error) {
	handle, err := os.Open(deliveryPath)
	if err != nil {
		return "", "", "", fmt.Errorf("open normalized image for presentation: %w", err)
	}
	defer handle.Close()
	decoded, _, err := image.Decode(handle)
	if err != nil {
		return "", "", "", fmt.Errorf(
			"decode normalized image for delivery descriptor: %w",
			err,
		)
	}
	dominantColor := sampledImageDominantColor(decoded)

	lqipPath := filepath.Join(workDir, "lqip.jpg")
	if _, err := runCommand(
		ctx,
		p.Config.FFmpegPath,
		"-hide_banner", "-loglevel", "error", "-y",
		"-i", deliveryPath,
		"-map", "0:v:0",
		"-frames:v", "1",
		"-vf", "scale=16:-2:flags=lanczos,setsar=1,format=yuvj420p",
		"-q:v", "8",
		lqipPath,
	); err != nil {
		if ctx.Err() != nil {
			return "", "", "", fmt.Errorf(
				"image delivery LQIP generation timed out: %w",
				ctx.Err(),
			)
		}
		return "", "", "", fmt.Errorf(
			"ffmpeg image delivery LQIP execution failed: %v",
			commandFailureSummary(err),
		)
	}
	lqipBytes, err := os.ReadFile(lqipPath)
	if err != nil || len(lqipBytes) == 0 {
		if err != nil {
			return "", "", "", fmt.Errorf(
				"read image delivery LQIP artifact: %w",
				err,
			)
		}
		return "", "", "", fmt.Errorf(
			"image delivery LQIP generation produced no artifact",
		)
	}
	lqip := "data:image/jpeg;base64," + base64.StdEncoding.EncodeToString(lqipBytes)
	if len(lqip) > mediamodel.MaxImageLQIPDataURIBytes {
		return "", "", "", &mediaprocessing.RejectionError{
			Reason: "image delivery LQIP exceeds descriptor size limit",
		}
	}
	contentProfile := "photographic"
	if deliveryMimeType == "image/png" {
		contentProfile = "alpha_graphic"
	}
	return dominantColor, lqip, contentProfile, nil
}

func sampledImageDominantColor(source image.Image) string {
	bounds := source.Bounds()
	width := bounds.Dx()
	height := bounds.Dy()
	if width <= 0 || height <= 0 {
		return "#000000"
	}
	const sampleAxis = 64
	stepX := max(1, width/sampleAxis)
	stepY := max(1, height/sampleAxis)
	var red, green, blue, samples uint64
	for y := bounds.Min.Y; y < bounds.Max.Y; y += stepY {
		for x := bounds.Min.X; x < bounds.Max.X; x += stepX {
			r, g, b, _ := source.At(x, y).RGBA()
			red += uint64(r >> 8)
			green += uint64(g >> 8)
			blue += uint64(b >> 8)
			samples++
		}
	}
	if samples == 0 {
		return "#000000"
	}
	return fmt.Sprintf(
		"#%02X%02X%02X",
		red/samples,
		green/samples,
		blue/samples,
	)
}

func (p *FFmpegMediaProcessor) normalizeImage(
	ctx context.Context,
	sourcePath string,
	deliveryPath string,
	deliveryMimeType string,
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
	switch deliveryMimeType {
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
	if _, err := runCommand(ctx, p.Config.FFmpegPath, args...); err != nil {
		if ctx.Err() != nil {
			return fmt.Errorf("image normalization timed out: %w", ctx.Err())
		}
		return fmt.Errorf(
			"ffmpeg image normalization execution failed: %v",
			commandFailureSummary(err),
		)
	}
	info, err := os.Stat(deliveryPath)
	if err != nil || info.Size() <= 0 {
		if err != nil {
			return fmt.Errorf("stat normalized image artifact: %w", err)
		}
		return fmt.Errorf("image normalization produced no delivery artifact")
	}
	return nil
}

func normalizedImageFormat(mimeType string, pixelFormat string) (string, string) {
	mimeType = strings.ToLower(strings.TrimSpace(strings.Split(mimeType, ";")[0]))
	pixelFormat = strings.ToLower(strings.TrimSpace(pixelFormat))
	if mimeType == "image/png" ||
		mimeType == "image/gif" ||
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
