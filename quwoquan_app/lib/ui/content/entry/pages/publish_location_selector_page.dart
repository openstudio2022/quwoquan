import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

class PublishLocationSelectorPage extends StatefulWidget {
  const PublishLocationSelectorPage({super.key, required this.locationService});

  final CreateLocationService locationService;

  @override
  State<PublishLocationSelectorPage> createState() =>
      _PublishLocationSelectorPageState();
}

class _PublishLocationSelectorPageState
    extends State<PublishLocationSelectorPage> {
  bool _loading = true;
  String? _error;
  bool _showOpenSettings = false;
  List<CreateLocationOption> _items = const <CreateLocationOption>[];
  double? _lastLat;
  double? _lastLng;

  @override
  void initState() {
    super.initState();
    unawaited(_loadNearby());
  }

  Future<void> _loadNearby() async {
    setState(() {
      _loading = true;
      _error = null;
      _showOpenSettings = false;
    });
    try {
      final perm = await widget.locationService.ensureLocationPermission();
      if (!mounted) return;

      if (perm.result == LocationPermissionResult.permanentlyDenied) {
        setState(() {
          _loading = false;
          _error = context.l10n.locationAppPermissionRequired;
          _showOpenSettings = true;
        });
        return;
      }
      if (perm.result == LocationPermissionResult.needApproval ||
          perm.position == null) {
        setState(() {
          _loading = false;
          _error = context.l10n.locationPermissionRequired;
        });
        return;
      }

      final pos = perm.position!;
      final items = await widget.locationService.nearby(
        lat: pos.latitude,
        lng: pos.longitude,
      );
      if (!mounted) return;
      setState(() {
        _items = items;
        _lastLat = pos.latitude;
        _lastLng = pos.longitude;
        _loading = false;
      });
    } on CloudException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = IntegrationLocationErrorCode.fromCode(
          e.code,
        ).toDisplayMessage(context.l10n);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = context.l10n.locationLoadFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      navigationBar: AppNavigationBar(
        middle: Text(
          l10n.locationNearbyTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: () => Navigator.of(context).pop(),
        ),
        trailing: AppNavigationBarIconButton(
          icon: CupertinoIcons.search,
          onPressed: () async {
            final navigator = Navigator.of(context);
            final result = await Navigator.of(context)
                .push<CreateLocationOption>(
                  CupertinoPageRoute<CreateLocationOption>(
                    builder: (_) => PublishLocationSearchPage(
                      locationService: widget.locationService,
                      lat: _lastLat,
                      lng: _lastLng,
                    ),
                  ),
                );
            if (!mounted || result == null) return;
            navigator.pop(result);
          },
        ),
      ),
      child: SafeArea(
          child: _loading
              ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const CupertinoActivityIndicator(),
                      SizedBox(height: AppSpacing.interGroupMd),
                      Text(
                        l10n.locationFetchingResult,
                        style: TextStyle(
                          fontSize: AppTypography.body,
                          color: isDark
                              ? CupertinoColors.white
                              : CupertinoColors.black,
                        ),
                      ),
                    ],
                  ),
                )
              : _error != null
              ? Center(child: _buildErrorCard(l10n, isDark))
              : ListView(
                  children: [
                    CupertinoListTile(
                      title: Text(l10n.locationHidden),
                      onTap: () => Navigator.of(
                        context,
                      ).pop(CreateLocationOption.hidden),
                    ),
                    for (final item in _items) _buildLocationTile(item),
                  ],
                ),
      ),
    );
  }

  /// 内联错误卡片（error-and-permission §1.4.1）：文案与主操作同区
  Widget _buildErrorCard(AppLocalizations l10n, bool isDark) {
    final errorColor = AppColors.error;
    final bg = isDark
        ? CupertinoColors.systemGrey6
        : CupertinoColors.systemBackground;
    return Container(
      margin: EdgeInsets.all(SettingsSemanticConstants.blockHorizontalPadding),
      padding: EdgeInsets.all(AppSpacing.interGroupLg),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.blockBorderRadius,
        ),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            CupertinoIcons.exclamationmark_triangle,
            size: AppSpacing.avatarUserMd,
            color: errorColor,
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Text(
            _error!,
            style: TextStyle(fontSize: AppTypography.lg, color: errorColor),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: AppSpacing.interGroupLg),
          _showOpenSettings
              ? CupertinoButton.filled(
                  onPressed: () async {
                    await widget.locationService.openAppSettings();
                    if (mounted) _loadNearby();
                  },
                  child: Text(l10n.locationOpenSettings),
                )
              : CupertinoButton.filled(
                  onPressed: _loadNearby,
                  child: Text(l10n.retry),
                ),
        ],
      ),
    );
  }

  Widget _buildLocationTile(CreateLocationOption item) {
    final subtitleParts = <String>[];
    if (item.address.trim().isNotEmpty) {
      subtitleParts.add(item.address.trim());
    }
    if (item.distanceMeters != null && item.distanceMeters! > 0) {
      subtitleParts.add('${item.distanceMeters}m');
    }
    return CupertinoListTile(
      title: Text(item.name),
      subtitle: subtitleParts.isEmpty ? null : Text(subtitleParts.join(' · ')),
      onTap: () => Navigator.of(context).pop(item),
    );
  }
}

class PublishLocationSearchPage extends StatefulWidget {
  const PublishLocationSearchPage({
    super.key,
    required this.locationService,
    this.lat,
    this.lng,
  });

  final CreateLocationService locationService;
  final double? lat;
  final double? lng;

  @override
  State<PublishLocationSearchPage> createState() =>
      _PublishLocationSearchPageState();
}

class _PublishLocationSearchPageState extends State<PublishLocationSearchPage> {
  final TextEditingController _controller = TextEditingController();
  Timer? _debounce;
  bool _loading = false;
  String? _error;
  List<CreateLocationOption> _items = const <CreateLocationOption>[];

  @override
  void dispose() {
    _debounce?.cancel();
    _controller.dispose();
    super.dispose();
  }

  void _onQueryChanged(String value) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 280), () {
      _performSearch(value.trim());
    });
  }

  Future<void> _performSearch(String q) async {
    if (q.isEmpty) {
      if (!mounted) return;
      setState(() {
        _items = const <CreateLocationOption>[];
        _error = null;
        _loading = false;
      });
      return;
    }
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final result = await widget.locationService.search(
        q,
        lat: widget.lat,
        lng: widget.lng,
      );
      if (!mounted) return;
      setState(() {
        _items = result;
        _loading = false;
      });
    } on CloudException catch (e) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = IntegrationLocationErrorCode.fromCode(
          e.code,
        ).toDisplayMessage(context.l10n);
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = context.l10n.locationLoadFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    return AppScaffold(
      navigationBar: AppNavigationBar(
        middle: Text(
          l10n.locationSearchTitle,
          style: AppNavigationSemanticConstants.barTitleTextStyle(isDark),
        ),
        leading: AppNavigationBarIconButton(
          icon: CupertinoIcons.xmark,
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      child: SafeArea(
        child: Column(
            children: [
              Padding(
                padding: EdgeInsets.all(AppSpacing.interGroupMd),
                child: AppSearchField(
                  controller: _controller,
                  autofocus: true,
                  onChanged: _onQueryChanged,
                  placeholder: l10n.locationSearchHint,
                ),
              ),
              Expanded(
                child: _loading
                    ? const Center(child: CupertinoActivityIndicator())
                    : _error != null
                    ? Center(child: _buildErrorCard(l10n, isDark))
                    : _items.isEmpty
                    ? Center(
                        child: Text(
                          l10n.locationSearchEmpty,
                          style: TextStyle(
                            color: CupertinoColors.systemGrey,
                            fontSize: AppTypography.body,
                          ),
                        ),
                      )
                    : ListView.builder(
                        itemCount: _items.length,
                        itemBuilder: (context, index) {
                          final item = _items[index];
                          return CupertinoListTile(
                            title: Text(item.name),
                            subtitle: item.address.trim().isEmpty
                                ? null
                                : Text(item.address.trim()),
                            onTap: () => Navigator.of(context).pop(item),
                          );
                        },
                      ),
              ),
            ],
          ),
      ),
    );
  }

  Widget _buildErrorCard(AppLocalizations l10n, bool isDark) {
    final errorColor = AppColors.error;
    final bg = isDark
        ? CupertinoColors.systemGrey6
        : CupertinoColors.systemBackground;
    return Container(
      margin: EdgeInsets.all(SettingsSemanticConstants.blockHorizontalPadding),
      padding: EdgeInsets.all(AppSpacing.interGroupLg),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(
          SettingsSemanticConstants.blockBorderRadius,
        ),
        border: Border.all(
          color: SettingsSemanticConstants.blockBorderColor(isDark),
        ),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            CupertinoIcons.exclamationmark_triangle,
            size: AppSpacing.avatarUserMd,
            color: errorColor,
          ),
          SizedBox(height: AppSpacing.interGroupMd),
          Text(
            _error!,
            style: TextStyle(fontSize: AppTypography.lg, color: errorColor),
            textAlign: TextAlign.center,
          ),
          SizedBox(height: AppSpacing.interGroupLg),
          CupertinoButton.filled(
            onPressed: () => _performSearch(_controller.text.trim()),
            child: Text(l10n.retry),
          ),
        ],
      ),
    );
  }
}
