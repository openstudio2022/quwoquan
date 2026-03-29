import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

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
  String? _error;
  List<Map<String, dynamic>> _files = const [];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFiles());
  }

  Future<void> _loadFiles() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final repo = ref.read(circleRepositoryProvider);
      final files = await repo.listFiles(widget.circleId);
      if (mounted) {
        setState(() {
          _files = files;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.toString();
        });
      }
    }
  }

  String _formatBytes(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1048576) return '${(bytes / 1024).toStringAsFixed(1)} KB';
    if (bytes < 1073741824) return '${(bytes / 1048576).toStringAsFixed(1)} MB';
    return '${(bytes / 1073741824).toStringAsFixed(1)} GB';
  }

  IconData _fileIcon(String? mimeType, String fileType) {
    if (fileType == 'folder') return CupertinoIcons.folder_fill;
    if (mimeType == null) return CupertinoIcons.doc;
    if (mimeType.startsWith('image/')) return CupertinoIcons.photo;
    if (mimeType.startsWith('video/')) return CupertinoIcons.videocam;
    if (mimeType.contains('pdf')) return CupertinoIcons.doc_text;
    if (mimeType.contains('spreadsheet') || mimeType.contains('excel')) {
      return CupertinoIcons.table;
    }
    return CupertinoIcons.doc;
  }

  Color _fileIconColor(String? mimeType, String fileType) {
    if (fileType == 'folder') return AppColors.warning;
    if (mimeType == null) return AppColors.primaryColor;
    if (mimeType.startsWith('image/')) return AppColors.primaryColor;
    if (mimeType.startsWith('video/')) return AppColors.secondaryColor;
    if (mimeType.contains('pdf')) return AppColors.error;
    return AppColors.secondaryColor;
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return _buildErrorCard();
    }

    final fgPrimary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    final borderColor = AppColorsFunctional.getColor(widget.isDark, ColorType.borderPrimary);
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
    ));
  }

  Widget _buildCapacityBar({
    required Color fgPrimary,
    required Color fgSecondary,
    required Color borderColor,
    required Color backgroundColor,
  }) {
    final usedRatio = widget.storageQuotaBytes > 0
        ? widget.storageUsedBytes / widget.storageQuotaBytes
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
                      UITextConstants.circleAssetsTab,
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
                  label: '已用',
                  value: _formatBytes(widget.storageUsedBytes),
                  fgPrimary: fgPrimary,
                  fgSecondary: fgSecondary,
                ),
              ),
              SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _StorageStatChip(
                  label: '剩余',
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
    Map<String, dynamic> file,
    Color fgPrimary,
    Color fgSecondary,
    Color borderColor,
    Color backgroundColor,
  ) {
    final name = file['name'] as String;
    final fileType = file['fileType'] as String;
    final mimeType = file['mimeType'] as String?;
    final sizeBytes = file['sizeBytes'] as int;
    final date = file['createdAt'] as String;

    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: () {},
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
                  color: _fileIconColor(mimeType, fileType).withValues(alpha: 0.15),
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
                      fileType == 'folder'
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
        onPressed: () {},
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              CupertinoIcons.cloud_upload,
              color: AppColors.white,
              size: AppSpacing.iconMedium,
            ),
            SizedBox(width: AppSpacing.sm),
            Text(
              UITextConstants.circleUploadFile,
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
    final fgSecondary = AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundSecondary);
    return Container(
      padding: EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.error_outline, color: AppColors.error, size: AppSpacing.iconLarge),
          SizedBox(height: AppSpacing.sm),
          Text(
            UITextConstants.loadFailed,
            style: TextStyle(color: fgSecondary, fontSize: AppTypography.base),
          ),
          SizedBox(height: AppSpacing.sm),
          CupertinoButton(
            onPressed: _loadFiles,
            child: Text(
              UITextConstants.retry,
              style: TextStyle(
                color: AppColors.primaryColor,
                fontSize: AppTypography.base,
              ),
            ),
          ),
        ],
      ),
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
            style: TextStyle(
              fontSize: AppTypography.xs,
              color: fgSecondary,
            ),
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
