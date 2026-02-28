import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/features/create/models/publish_settings_models.dart';
import 'package:quwoquan_app/features/create/services/publish_settings_services.dart';

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
  List<CreateLocationOption> _items = const <CreateLocationOption>[];

  @override
  void initState() {
    super.initState();
    unawaited(_loadNearby());
  }

  Future<void> _loadNearby() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final items = await widget.locationService.nearby();
      if (!mounted) {
        return;
      }
      setState(() {
        _items = items;
        _loading = false;
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _loading = false;
        _error = UITextConstants.locationLoadFailed;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        title: const Text(UITextConstants.locationNearbyTitle),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.search),
            onPressed: () async {
              final navigator = Navigator.of(context);
              final result = await Navigator.of(context)
                  .push<CreateLocationOption>(
                    CupertinoPageRoute<CreateLocationOption>(
                      builder: (_) => PublishLocationSearchPage(
                        locationService: widget.locationService,
                      ),
                    ),
                  );
              if (!mounted || result == null) {
                return;
              }
              navigator.pop(result);
            },
          ),
        ],
      ),
      body: _loading
          ? Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: const [
                  CircularProgressIndicator(),
                  SizedBox(height: 12),
                  Text(UITextConstants.locationSearchingNearby),
                ],
              ),
            )
          : _error != null
          ? Center(
              child: Padding(
                padding: EdgeInsets.all(AppSpacing.interGroupLg),
                child: Text(
                  _error!,
                  style: textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context).colorScheme.error,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            )
          : ListView(
              children: [
                ListTile(
                  title: const Text(UITextConstants.locationHidden),
                  onTap: () =>
                      Navigator.of(context).pop(CreateLocationOption.hidden),
                ),
                for (final item in _items) _buildLocationTile(item),
              ],
            ),
      floatingActionButton: _error != null
          ? FloatingActionButton(
              onPressed: _loadNearby,
              child: const Icon(Icons.refresh),
            )
          : null,
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
    return ListTile(
      title: Text(item.name),
      subtitle: subtitleParts.isEmpty ? null : Text(subtitleParts.join(' · ')),
      onTap: () => Navigator.of(context).pop(item),
    );
  }
}

class PublishLocationSearchPage extends StatefulWidget {
  const PublishLocationSearchPage({super.key, required this.locationService});

  final CreateLocationService locationService;

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
    _debounce = Timer(const Duration(milliseconds: 280), () async {
      final q = value.trim();
      if (q.isEmpty) {
        setState(() {
          _items = const <CreateLocationOption>[];
          _error = null;
          _loading = false;
        });
        return;
      }
      setState(() {
        _loading = true;
        _error = null;
      });
      try {
        final result = await widget.locationService.search(q);
        if (!mounted) {
          return;
        }
        setState(() {
          _items = result;
          _loading = false;
        });
      } catch (_) {
        if (!mounted) {
          return;
        }
        setState(() {
          _loading = false;
          _error = UITextConstants.locationLoadFailed;
        });
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text(UITextConstants.locationSearchTitle),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Padding(
            padding: EdgeInsets.all(AppSpacing.interGroupMd),
            child: TextField(
              controller: _controller,
              autofocus: true,
              onChanged: _onQueryChanged,
              decoration: const InputDecoration(
                hintText: UITextConstants.locationSearchHint,
                prefixIcon: Icon(Icons.search),
              ),
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _error != null
                ? Center(
                    child: Text(
                      _error!,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.error,
                      ),
                    ),
                  )
                : _items.isEmpty
                ? const Center(child: Text(UITextConstants.locationSearchEmpty))
                : ListView.builder(
                    itemCount: _items.length,
                    itemBuilder: (context, index) {
                      final item = _items[index];
                      return ListTile(
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
    );
  }
}
