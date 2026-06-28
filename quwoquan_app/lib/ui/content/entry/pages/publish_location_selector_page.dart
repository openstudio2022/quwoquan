import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/app/navigation/page_access_internal_routes.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/ui/content/entry/models/publish_settings_models.dart';
import 'package:quwoquan_app/ui/content/entry/services/publish_settings_services.dart';
import 'package:quwoquan_app/l10n/l10n.dart';

/// 发布选点；列表项 [CreateLocationOption] ← 云 [LocationPoiDto]。
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
  UiErrorSemantic? _errorSemantic;
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
      _errorSemantic = null;
    });
    try {
      final perm = await widget.locationService.ensureLocationPermission();
      if (!mounted) return;

      if (perm.result == LocationPermissionResult.permanentlyDenied) {
        setState(() {
          _loading = false;
          _errorSemantic = UiErrorSemanticResolver.resolve(
            context,
            error: CloudException(
              type: CloudErrorType.forbidden,
              message: context.l10n.locationAppPermissionRequired,
            ),
            category: UiErrorCategory.permissionRequired,
            scope: UiErrorScope.page,
            allowRetry: false,
            allowOpenSettings: true,
          );
        });
        return;
      }
      if (perm.result == LocationPermissionResult.needApproval ||
          perm.position == null) {
        setState(() {
          _loading = false;
          _errorSemantic = UiErrorSemanticResolver.resolve(
            context,
            error: CloudException(
              type: CloudErrorType.forbidden,
              message: context.l10n.locationPermissionRequired,
            ),
            category: UiErrorCategory.permissionRequired,
            scope: UiErrorScope.page,
            allowOpenSettings: false,
          );
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
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: e,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorSemantic = UiErrorSemanticResolver.resolve(
          context,
          error: CloudException(
            type: CloudErrorType.unknown,
            message: context.l10n.locationLoadFailed,
          ),
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
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
                    settings: const RouteSettings(
                      name: PageAccessInternalRoutes.publishLocationSearch,
                    ),
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
              : _errorSemantic != null
              ? AppPageErrorState(
                  semantic: _errorSemantic!,
                  onAction: _handleErrorAction,
                )
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

  Future<void> _handleErrorAction(UiErrorAction action) async {
    switch (action.type) {
      case UiErrorActionType.openSettings:
        await AppPermissionCoordinator.instance.openSettings(
          AppPermissionKind.location,
          onReturn: (granted) {
            if (mounted && granted) {
              unawaited(_loadNearby());
            }
          },
        );
        return;
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        await _loadNearby();
        return;
      case UiErrorActionType.login:
      case UiErrorActionType.back:
      case UiErrorActionType.dismiss:
        if (mounted && Navigator.of(context).canPop()) {
          Navigator.of(context).pop();
        }
        return;
    }
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
  UiErrorSemantic? _errorSemantic;
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
        _errorSemantic = null;
        _loading = false;
      });
      return;
    }
    if (!mounted) return;
    setState(() {
      _loading = true;
      _errorSemantic = null;
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
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: e,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorSemantic = UiErrorSemanticResolver.resolve(
          context,
          error: CloudException(
            type: CloudErrorType.unknown,
            message: context.l10n.locationLoadFailed,
          ),
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
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
              : _errorSemantic != null
                    ? AppPageErrorState(
                        semantic: _errorSemantic!,
                        onAction: _handleSearchErrorAction,
                      )
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

  Future<void> _handleSearchErrorAction(UiErrorAction action) async {
    switch (action.type) {
      case UiErrorActionType.retry:
      case UiErrorActionType.resubmit:
        await _performSearch(_controller.text.trim());
        return;
      case UiErrorActionType.dismiss:
      case UiErrorActionType.back:
      case UiErrorActionType.login:
      case UiErrorActionType.openSettings:
        return;
    }
  }
}
