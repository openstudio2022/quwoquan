import 'dart:async';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/application/content/media/content_media_upload_coordinator.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:url_launcher/url_launcher.dart';

/// 圈子存储空间板块：容量条 + 文件列表 + 上传按钮（含独立 loading/error 状态）
class SectionStorage extends ConsumerStatefulWidget {
  const SectionStorage({
    super.key,
    required this.circleId,
    required this.isDark,
    required this.storageUsedBytes,
    required this.storageQuotaBytes,
  });

  final String circleId;
  final bool isDark;
  final int storageUsedBytes;
  final int storageQuotaBytes;

  @override
  ConsumerState<SectionStorage> createState() => _SectionStorageState();
}

class _SectionStorageState extends ConsumerState<SectionStorage> {
  bool _isLoading = true;
  bool _isMutating = false;
  UiErrorSemantic? _errorSemantic;
  List<CircleFileSlice> _files = const [];
  final List<String?> _folderPath = <String?>[null];

  String? get _parentFolderId => _folderPath.last;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFiles());
  }

  Future<void> _loadFiles() async {
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
    });
    try {
      final files = await ref
          .read(circleDetailFileQueryProvider)
          .list(
            CircleFileListQuery(
              circleId: widget.circleId,
              parentFolderId: _parentFolderId,
              limit: 100,
            ),
          );
      if (mounted) {
        setState(() {
          _files = files.items;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorSemantic = runtimeErrorSemantic(
            context,
            error: e,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
        });
      }
    }
  }

  Future<void> _openEntry(CircleFileSlice file) async {
    if (file.fileType == CircleFileType.folder) {
      setState(() => _folderPath.add(file.fileId));
      await _loadFiles();
      return;
    }
    final assetId = file.assetId;
    if (assetId == null) {
      _setActionFailure(StateError('CircleFile asset reference is missing'));
      return;
    }
    setState(() => _isMutating = true);
    try {
      final grant = await ref
          .read(circleDetailContentMediaFacetProvider)
          .requestOriginalAccess(
            RequestContentMediaOriginalAccessCommand(mediaId: assetId),
          );
      final launched = await launchUrl(
        grant.originalUrl,
        mode: ref.read(platformCapabilitiesProvider).hasLocalFileSystem
            ? LaunchMode.externalApplication
            : LaunchMode.platformDefault,
      );
      if (!launched) throw StateError('platform rejected the media access URL');
    } catch (error) {
      _setActionFailure(error);
    } finally {
      if (mounted) setState(() => _isMutating = false);
    }
  }

  Future<void> _backToParent() async {
    if (_folderPath.length <= 1) return;
    setState(() => _folderPath.removeLast());
    await _loadFiles();
  }

  Future<void> _pickAndUpload() async {
    final file = await FilePicker.pickFile();
    if (file == null) return;
    setState(() {
      _isMutating = true;
      _errorSemantic = null;
    });
    try {
      final coordinator = ContentMediaUploadCoordinator(
        media: ref.read(circleDetailContentMediaFacetProvider),
        telemetry: ref.read(appTelemetryReporterProvider),
      );
      final path = file.path?.trim() ?? '';
      final source = path.isNotEmpty
          ? await ref.read(contentMediaSourceReaderProvider).prepare(path)
          : await prepareContentMediaSource(
              fileSize: await file.length(),
              openRead: file.readAsByteStream,
            );
      final uploaded = await coordinator.uploadPreparedSource(
        source: source,
        mediaType: MediaType.file,
        mimeType: 'application/octet-stream',
        uploadStream: ref.read(contentMediaStreamObjectUploadProvider),
      );
      await ref
          .read(circleDetailFileCommandWriterProvider)
          .create(
            CreateCircleFileCommand(
              circleId: widget.circleId,
              parentFolderId: _parentFolderId,
              name: file.name,
              fileType: CircleFileType.file,
              assetId: uploaded.assetId,
            ),
          );
      await _loadFiles();
    } catch (error) {
      _setActionFailure(error);
    } finally {
      if (mounted) setState(() => _isMutating = false);
    }
  }

  void _setActionFailure(Object error) {
    if (!mounted) return;
    setState(() {
      _errorSemantic = runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.submit,
        scope: UiErrorScope.section,
      );
    });
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1048576) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1073741824) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
  }

  IconData _fileIcon(String? mimeType, CircleFileType fileType) {
    if (fileType == CircleFileType.folder) return CupertinoIcons.folder_fill;
    if (mimeType == null) return CupertinoIcons.doc;
    if (mimeType.startsWith('image/')) return CupertinoIcons.photo;
    if (mimeType.startsWith('video/')) return CupertinoIcons.videocam;
    if (mimeType.contains('pdf')) return CupertinoIcons.doc_text;
    if (mimeType.contains('spreadsheet') || mimeType.contains('excel')) {
      return CupertinoIcons.table;
    }
    return CupertinoIcons.doc;
  }

  Color _fileIconColor(String? mimeType, CircleFileType fileType) {
    if (fileType == CircleFileType.folder) return AppColors.warning;
    if (mimeType == null) return AppColors.primaryColor;
    if (mimeType.startsWith('image/')) return AppColors.primaryColor;
    if (mimeType.startsWith('video/')) return AppColors.secondaryColor;
    if (mimeType.contains('pdf')) return AppColors.error;
    return AppColors.secondaryColor;
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return AppRequestFeedback.section();
    }
    if (_errorSemantic != null) {
      return _buildErrorCard();
    }

    final fgPrimary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );
    final bgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundSecondary,
    );

    return Padding(
      padding: EdgeInsets.all(AppSpacing.containerSm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildCapacityBar(
            fgPrimary: fgPrimary,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: bgSecondary,
          ),
          SizedBox(height: AppSpacing.md),
          if (_folderPath.length > 1) ...[
            CupertinoButton(
              padding: EdgeInsets.zero,
              onPressed: _isMutating ? null : () => unawaited(_backToParent()),
              child: Text(CommunityText.circleStorageBackToParent),
            ),
            SizedBox(height: AppSpacing.sm),
          ],
          if (_files.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.md),
              child: Text(
                CommunityText.noData,
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  color: fgSecondary,
                ),
              ),
            ),
          ..._files.map(
            (file) => _buildFileItem(
              file,
              fgPrimary,
              fgSecondary,
              borderColor,
              bgSecondary,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          _buildUploadButton(),
        ],
      ),
    );
  }

  Widget _buildCapacityBar({
    required Color fgPrimary,
    required Color fgSecondary,
    required Color borderColor,
    required Color backgroundColor,
  }) {
    final usedRatio = widget.storageQuotaBytes > 0
        ? (widget.storageUsedBytes / widget.storageQuotaBytes).clamp(0.0, 1.0)
        : 0.0;
    final remainingBytes = (widget.storageQuotaBytes - widget.storageUsedBytes)
        .clamp(0, widget.storageQuotaBytes);
    return Container(
      padding: EdgeInsets.all(AppSpacing.containerMd),
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: borderColor.withValues(alpha: 0.12)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: AppSpacing.buttonHeight,
                height: AppSpacing.buttonHeight,
                decoration: BoxDecoration(
                  color: AppColors.primaryColor.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
                child: Icon(
                  CupertinoIcons.folder_fill,
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconMedium,
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      CommunityText.circleAssetsTab,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.semiBold,
                        color: fgPrimary,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      '${_formatBytes(widget.storageUsedBytes)} / ${_formatBytes(widget.storageQuotaBytes)}',
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                '${(usedRatio * 100).toStringAsFixed(1)}%',
                style: TextStyle(
                  fontSize: AppTypography.sm,
                  fontWeight: AppTypography.semiBold,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.md),
          ClipRRect(
            borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
            child: LinearProgressIndicator(
              value: usedRatio,
              backgroundColor: fgSecondary.withValues(alpha: 0.15),
              valueColor: AlwaysStoppedAnimation<Color>(
                usedRatio > 0.9 ? AppColors.error : AppColors.primaryColor,
              ),
              minHeight: AppSpacing.xs,
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: _StorageStatChip(
                  label: CommunityText.circleStorageUsed,
                  value: _formatBytes(widget.storageUsedBytes),
                  fgPrimary: fgPrimary,
                  fgSecondary: fgSecondary,
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _StorageStatChip(
                  label: CommunityText.circleStorageRemaining,
                  value: _formatBytes(remainingBytes),
                  fgPrimary: fgPrimary,
                  fgSecondary: fgSecondary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildFileItem(
    CircleFileSlice file,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
    Color backgroundColor,
  ) {
    final name = file.name;
    final fileType = file.fileType;
    final mimeType = file.mimeType;
    final sizeBytes = file.sizeBytes;
    final date = file.createdAt.toIso8601String().split('T').first;

    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: _isMutating ? null : () => unawaited(_openEntry(file)),
        child: Container(
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor.withValues(alpha: 0.12)),
          ),
          child: Row(
            children: [
              Container(
                width: AppSpacing.largeButtonSize,
                height: AppSpacing.largeButtonSize,
                decoration: BoxDecoration(
                  color: _fileIconColor(
                    mimeType,
                    fileType,
                  ).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                ),
                child: Icon(
                  _fileIcon(mimeType, fileType),
                  color: _fileIconColor(mimeType, fileType),
                  size: AppSpacing.iconMedium,
                ),
              ),
              SizedBox(width: AppSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.medium,
                        color: fgPrimary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    SizedBox(height: AppSpacing.xs),
                    Text(
                      fileType == CircleFileType.folder
                          ? date
                          : '${_formatBytes(sizeBytes)} · $date',
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              Icon(
                CupertinoIcons.chevron_forward,
                color: fgSecondary,
                size: AppSpacing.iconSmall,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildUploadButton() {
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        color: AppColors.primaryColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        onPressed: _isMutating ? null : () => unawaited(_pickAndUpload()),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (_isMutating)
              AppRequestFeedback.inline(indicatorColor: AppColors.white)
            else
              Icon(
                CupertinoIcons.cloud_upload,
                color: AppColors.white,
                size: AppSpacing.iconMedium,
              ),
            SizedBox(width: AppSpacing.sm),
            Text(
              CommunityText.circleUploadFile,
              style: TextStyle(
                color: AppColors.white,
                fontSize: AppTypography.base,
                fontWeight: AppTypography.semiBold,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard() {
    return AppSectionErrorCard(
      semantic: _errorSemantic!,
      margin: EdgeInsets.zero,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _loadFiles();
        }
      },
    );
  }
}

class _StorageStatChip extends StatelessWidget {
  const _StorageStatChip({
    required this.label,
    required this.value,
    required this.fgPrimary,
    required this.fgSecondary,
  });

  final String label;
  final String value;
  final Color fgPrimary;
  final Color fgSecondary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: fgSecondary.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: TextStyle(fontSize: AppTypography.xs, color: fgSecondary),
          ),
          SizedBox(height: AppSpacing.intraGroupXs / 2),
          Text(
            value,
            style: TextStyle(
              fontSize: AppTypography.sm,
              fontWeight: AppTypography.semiBold,
              color: fgPrimary,
            ),
          ),
        ],
      ),
    );
  }
}
