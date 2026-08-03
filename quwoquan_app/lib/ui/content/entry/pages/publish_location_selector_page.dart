import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/app/navigation/generated/page_access_internal_routes.g.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/integration_location_errors.g.dart';
import 'package:quwoquan_app/core/application/content/create_location_coordinator.dart';
import 'package:quwoquan_app/core/constants/navigation_semantic_constants.dart';
import 'package:quwoquan_app/core/platform/location/location_gateway.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';
import 'package:quwoquan_app/core/widgets/app_scaffold.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/ui/content/models/publish_settings_models.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

CloudException _locationPermissionFailure() {
  final code = IntegrationLocationErrorCode.locationPermissionRequired.code;
  final failure = RuntimeFailure(
    code: code,
    origin: RuntimeFailureOrigin.localClient,
    kind: RuntimeFailureKind.permission,
    nature: RuntimeFailureNature.requiresPermission,
    location: const RuntimeFailureLocation(
      businessObject: 'integration.location',
      functionModule: 'publish_location_selector',
    ),
    context: const RuntimeFailureContext(),
  );
  return CloudException(
    type: CloudErrorType.forbidden,
    message: code,
    statusCode: 403,
    code: code,
    runtimeFailure: failure,
  );
}

/// 发布选点；页面只消费应用协调器，不直接拼装 Cloud 请求。
class PublishLocationSelectorPage extends StatefulWidget {
  const PublishLocationSelectorPage({
    super.key,
    required this.locationCoordinator,
  });

  final CreateLocationCoordinator locationCoordinator;

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
      final access = await widget.locationCoordinator.ensureLocationAccess();
      if (!mounted) return;

      if (access.permission == LocationPermissionResult.permanentlyDenied) {
        setState(() {
          _loading = false;
          _errorSemantic = UiErrorSemanticResolver.resolve(
            context,
            error: _locationPermissionFailure(),
            category: UiErrorCategory.permissionRequired,
            scope: UiErrorScope.page,
            allowRetry: false,
            allowOpenSettings: true,
          );
        });
        return;
      }
      if (access.permission == LocationPermissionResult.needApproval ||
          access.position == null) {
        setState(() {
          _loading = false;
          _errorSemantic = UiErrorSemanticResolver.resolve(
            context,
            error: _locationPermissionFailure(),
            category: UiErrorCategory.permissionRequired,
            scope: UiErrorScope.page,
            allowOpenSettings: false,
          );
        });
        return;
      }

      final position = access.position!;
      final pois = await widget.locationCoordinator.nearby(
        latitude: position.latitude,
        longitude: position.longitude,
      );
      final items = pois;
      if (!mounted) return;
      setState(() {
        _items = items;
        _lastLat = position.latitude;
        _lastLng = position.longitude;
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
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: CloudErrorMapper.fromException(error),
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
                      locationCoordinator: widget.locationCoordinator,
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
            ? AppRequestFeedback.page()
            : _errorSemantic != null
            ? AppPageErrorState(
                semantic: ensureRetryUiErrorSemantic(_errorSemantic!),
                onAction: _handleErrorAction,
              )
            : ListView(
                children: [
                  CupertinoListTile(
                    title: Text(l10n.locationHidden),
                    onTap: () =>
                        Navigator.of(context).pop(CreateLocationOption.hidden),
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
      case UiErrorActionType.openUpdate:
      case UiErrorActionType.dismiss:
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
    required this.locationCoordinator,
    this.lat,
    this.lng,
  });

  final CreateLocationCoordinator locationCoordinator;
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
      final result = await widget.locationCoordinator.search(
        q,
        latitude: widget.lat,
        longitude: widget.lng,
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
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: CloudErrorMapper.fromException(error),
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
                  ? AppRequestFeedback.section()
                  : _errorSemantic != null
                  ? AppPageErrorState(
                      semantic: ensureRetryUiErrorSemantic(_errorSemantic!),
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
      case UiErrorActionType.login:
      case UiErrorActionType.openSettings:
      case UiErrorActionType.openUpdate:
        return;
    }
  }
}
