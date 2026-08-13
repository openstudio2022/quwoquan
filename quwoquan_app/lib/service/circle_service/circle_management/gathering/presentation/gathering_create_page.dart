import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/domain/gathering_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/application/public/gathering_presentation_models.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_page_copy.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/gathering/presentation/gathering_widgets.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/layout/app_scaffold.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/di/gathering_dependencies.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

enum GatheringCreateSubmissionStep {
  ready,
  creatingDraft,
  draftCreated,
  roomReady,
  publishing,
  published,
}

class GatheringCreatePage extends ConsumerStatefulWidget {
  const GatheringCreatePage({
    super.key,
    required this.copy,
    required this.initialValue,
    this.onPublished,
  });

  static const viewKey = ValueKey<String>('gathering-create-page');
  static const submitKey = ValueKey<String>('gathering-create-submit');
  static const retryKey = ValueKey<String>('gathering-create-retry');
  static const statusKey = ValueKey<String>('gathering-create-status');
  static const startAtFieldKey = ValueKey<String>('gathering-create-start-at');
  static const endAtFieldKey = ValueKey<String>('gathering-create-end-at');
  static const admissionClosesFieldKey = ValueKey<String>(
    'gathering-create-admission-closes',
  );

  final GatheringCreatePageCopy copy;
  final GatheringCreateInitialValue initialValue;
  final ValueChanged<GatheringCommandResult>? onPublished;

  @override
  ConsumerState<GatheringCreatePage> createState() =>
      _GatheringCreatePageState();
}

enum _GatheringDatePickerSlot { none, startAt, endAt, admissionClosesAt }

class _GatheringCreatePageState extends ConsumerState<GatheringCreatePage> {
  late final TextEditingController _titleController;
  late final TextEditingController _summaryController;
  late final TextEditingController _coarsePlaceController;
  late final TextEditingController _exactMeetingPointController;
  late final TextEditingController _onlineLocationController;
  late final TextEditingController _capacityController;

  late GatheringPlaceMode _placeMode;
  late GatheringAudiencePolicy _audience;
  late GatheringAdmissionPolicy _admission;
  late GatheringTimeDisclosure _timeDisclosure;
  late GatheringPlaceDisclosure _placeDisclosure;
  late GatheringRosterDisclosure _rosterDisclosure;
  late bool _creatorParticipates;
  late DateTime _startAt;
  late DateTime _endAt;
  DateTime? _admissionClosesAt;
  _GatheringDatePickerSlot _expandedPicker = _GatheringDatePickerSlot.none;

  GatheringCreateSubmissionStep _step = GatheringCreateSubmissionStep.ready;
  GatheringCommandResult? _draftResult;
  Object? _submissionError;
  bool _validationFailed = false;
  late final String _intentKey;

  bool get _isSubmitting => switch (_step) {
    GatheringCreateSubmissionStep.creatingDraft ||
    GatheringCreateSubmissionStep.publishing => true,
    _ => false,
  };

  @override
  void initState() {
    super.initState();
    final initial = widget.initialValue;
    _titleController = TextEditingController(text: initial.purpose.title);
    _summaryController = TextEditingController(text: initial.purpose.summary);
    _coarsePlaceController = TextEditingController(
      text: initial.place.coarsePlaceLabel,
    );
    _exactMeetingPointController = TextEditingController(
      text: initial.place.exactMeetingPoint,
    );
    _onlineLocationController = TextEditingController(
      text: initial.place.onlineLocationRef,
    );
    _capacityController = TextEditingController(
      text: initial.policy.maxParticipants.toString(),
    );
    _startAt = initial.schedule.startAt;
    _endAt = initial.schedule.endAt;
    _admissionClosesAt = initial.schedule.admissionClosesAt;
    _placeMode = initial.place.mode;
    _audience = initial.policy.audience;
    _admission = initial.policy.admission;
    _timeDisclosure = initial.policy.disclosure.time;
    _placeDisclosure = initial.policy.disclosure.place;
    _rosterDisclosure = initial.policy.disclosure.roster;
    _creatorParticipates = initial.creatorParticipates;
    _intentKey =
        'gathering-create-${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
  }

  @override
  void dispose() {
    _titleController.dispose();
    _summaryController.dispose();
    _coarsePlaceController.dispose();
    _exactMeetingPointController.dispose();
    _onlineLocationController.dispose();
    _capacityController.dispose();
    super.dispose();
  }

  GatheringCreateDraftInput? _buildInput() {
    // 发起身份、授权凭证与安全策略由生产 composer 注入，不再暴露为表单字段。
    final host = widget.initialValue.host;
    final capacity = int.tryParse(_capacityController.text.trim());
    final hasPhysicalPlace =
        _placeMode == GatheringPlaceMode.physical ||
        _placeMode == GatheringPlaceMode.hybrid;
    final hasOnlinePlace =
        _placeMode == GatheringPlaceMode.online ||
        _placeMode == GatheringPlaceMode.hybrid;
    final valid =
        _titleController.text.trim().isNotEmpty &&
        _summaryController.text.trim().isNotEmpty &&
        _endAt.isAfter(_startAt) &&
        (capacity ?? 0) > 0 &&
        (!hasPhysicalPlace ||
            (_coarsePlaceController.text.trim().isNotEmpty &&
                _exactMeetingPointController.text.trim().isNotEmpty)) &&
        (!hasOnlinePlace || _onlineLocationController.text.trim().isNotEmpty);
    if (!valid) {
      return null;
    }
    return GatheringCreateDraftInput(
      idempotencyKey: _intentKey,
      host: host,
      creatorParticipates: _creatorParticipates,
      purpose: GatheringPurposeDraft(
        title: _titleController.text.trim(),
        summary: _summaryController.text.trim(),
        sourceRefs: widget.initialValue.purpose.sourceRefs,
        topicRefs: widget.initialValue.purpose.topicRefs,
        requirementRefs: widget.initialValue.purpose.requirementRefs,
      ),
      schedule: GatheringScheduleDraft(
        timezone: widget.initialValue.schedule.timezone,
        startAt: _startAt,
        endAt: _endAt,
        admissionClosesAt: _admissionClosesAt,
      ),
      place: GatheringPlaceDraft(
        mode: _placeMode,
        coarsePlaceRef: widget.initialValue.place.coarsePlaceRef,
        coarsePlaceLabel: _coarsePlaceController.text.trim(),
        exactMeetingPoint: _exactMeetingPointController.text.trim(),
        onlineLocationRef: _onlineLocationController.text.trim(),
      ),
      policy: GatheringPolicyDraft(
        audience: _audience,
        admission: _admission,
        maxParticipants: capacity!,
        disclosure: GatheringDisclosurePolicyDraft(
          time: _timeDisclosure,
          place: _placeDisclosure,
          roster: _rosterDisclosure,
        ),
        riskControlPolicyRef: widget.initialValue.policy.riskControlPolicyRef,
      ),
    );
  }

  RuntimeFailure _roomPendingFailure() {
    return const RuntimeFailure(
      code: RuntimeFailureCodes.appSystemUnknownError,
      semanticReason: 'gathering_room_not_ready',
      origin: RuntimeFailureOrigin.environment,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: RuntimeFailureLocation(
        businessObject: 'circle.gathering',
        functionModule: 'gathering_create_page',
      ),
      context: RuntimeFailureContext(),
      recovery: RuntimeRecoveryDirective(
        action: 'retry',
        disruptionLevel: 'inlineCard',
      ),
    );
  }

  Future<void> _submit() async {
    if (_isSubmitting || _step == GatheringCreateSubmissionStep.published) {
      return;
    }
    final input = _buildInput();
    if (input == null) {
      setState(() {
        _validationFailed = true;
        _submissionError = null;
      });
      return;
    }
    setState(() {
      _validationFailed = false;
      _submissionError = null;
    });
    final writer = ref.read(gatheringCommandWriterProvider);
    try {
      var result = _draftResult;
      if (result == null) {
        setState(() => _step = GatheringCreateSubmissionStep.creatingDraft);
        result = await writer.createDraft(input);
        if (!mounted) return;
        setState(() {
          _draftResult = result;
          _step = GatheringCreateSubmissionStep.draftCreated;
        });
      }

      if (result.roomBindingStatus != GatheringRoomBindingStatus.ready) {
        setState(() => _step = GatheringCreateSubmissionStep.draftCreated);
        throw _roomPendingFailure();
      }
      final conversationId = result.conversationId?.trim();
      if (conversationId == null || conversationId.isEmpty) {
        throw _roomPendingFailure();
      }
      setState(() => _step = GatheringCreateSubmissionStep.roomReady);

      setState(() => _step = GatheringCreateSubmissionStep.publishing);
      result = await writer.publish(
        GatheringVersionCommandInput(
          idempotencyKey: '$_intentKey:publish',
          gatheringId: result.gatheringId,
          expectedGatheringVersion: result.aggregateVersion,
        ),
      );
      if (!mounted) return;
      setState(() {
        _draftResult = result;
        _step = GatheringCreateSubmissionStep.published;
      });
      widget.onPublished?.call(result);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _submissionError = error;
        final result = _draftResult;
        _step = result?.roomBindingStatus == GatheringRoomBindingStatus.ready
            ? GatheringCreateSubmissionStep.roomReady
            : result == null
            ? GatheringCreateSubmissionStep.ready
            : GatheringCreateSubmissionStep.draftCreated;
      });
    }
  }

  String _stepLabel() => switch (_step) {
    GatheringCreateSubmissionStep.ready ||
    GatheringCreateSubmissionStep.creatingDraft => widget.copy.draftStepLabel,
    GatheringCreateSubmissionStep.draftCreated => widget.copy.roomStepLabel,
    GatheringCreateSubmissionStep.roomReady ||
    GatheringCreateSubmissionStep.publishing => widget.copy.publishStepLabel,
    GatheringCreateSubmissionStep.published => widget.copy.completedStepLabel,
  };

  Widget _gap() => SizedBox(height: AppSpacing.intraGroupSm);

  @override
  Widget build(BuildContext context) {
    final background = AppColors.iosPageBackground(context);
    return AppScaffold(
      key: GatheringCreatePage.viewKey,
      backgroundColor: background,
      navigationBar: AppNavigationBar(
        backgroundColor: background,
        middle: Text(widget.copy.pageTitle),
      ),
      body: GatheringPageBody(
        bottom: Semantics(
          button: true,
          label: _submissionError == null
              ? widget.copy.submitAction
              : widget.copy.retryAction,
          child: SizedBox(
            width: double.infinity,
            child: CupertinoButton.filled(
              key: _submissionError == null
                  ? GatheringCreatePage.submitKey
                  : GatheringCreatePage.retryKey,
              onPressed: _isSubmitting ? null : () => unawaited(_submit()),
              child: _isSubmitting
                  ? AppRequestFeedback.inline(
                      indicatorColor: CupertinoColors.white,
                    )
                  : Text(
                      _submissionError == null
                          ? widget.copy.submitAction
                          : widget.copy.retryAction,
                    ),
            ),
          ),
        ),
        children: <Widget>[
          _purposeSection(),
          SizedBox(height: AppSpacing.interGroupMd),
          _scheduleSection(),
          SizedBox(height: AppSpacing.interGroupMd),
          _placeSection(),
          SizedBox(height: AppSpacing.interGroupMd),
          _policySection(),
          SizedBox(height: AppSpacing.interGroupMd),
          _submissionStatus(),
        ],
      ),
    );
  }

  Widget _purposeSection() {
    return GatheringSectionCard(
      title: widget.copy.purposeSection,
      child: Column(
        children: <Widget>[
          GatheringLabeledTextField(
            label: widget.copy.titleLabel,
            controller: _titleController,
            placeholder: widget.copy.titlePlaceholder,
          ),
          _gap(),
          GatheringLabeledTextField(
            label: widget.copy.summaryLabel,
            controller: _summaryController,
            placeholder: widget.copy.summaryPlaceholder,
            maxLines: 3,
          ),
          _gap(),
          GatheringFactRow(
            label: widget.copy.sourceReferencesLabel,
            value: widget.initialValue.purpose.sourceRefs.length.toString(),
          ),
        ],
      ),
    );
  }

  String _formatDateTime(DateTime value) {
    final hour = value.hour.toString().padLeft(2, '0');
    final minute = value.minute.toString().padLeft(2, '0');
    return '${value.month}月${value.day}日 $hour:$minute';
  }

  void _togglePicker(_GatheringDatePickerSlot slot) {
    setState(() {
      _expandedPicker = _expandedPicker == slot
          ? _GatheringDatePickerSlot.none
          : slot;
    });
  }

  Widget _dateTimeField({
    required Key key,
    required String label,
    required _GatheringDatePickerSlot slot,
    required DateTime value,
    required ValueChanged<DateTime> onChanged,
  }) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final secondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final expanded = _expandedPicker == slot;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          button: true,
          label: label,
          value: _formatDateTime(value),
          child: CupertinoButton(
            key: key,
            padding: EdgeInsets.zero,
            onPressed: () => _togglePicker(slot),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(
                      color: foreground,
                      fontSize: AppTypography.base,
                    ),
                  ),
                ),
                Text(
                  _formatDateTime(value),
                  style: TextStyle(
                    color: expanded ? AppColors.primaryColor : secondary,
                    fontSize: AppTypography.base,
                  ),
                ),
              ],
            ),
          ),
        ),
        if (expanded)
          SizedBox(
            height: AppSpacing.oneHundredSixty + AppSpacing.twenty,
            child: CupertinoDatePicker(
              mode: CupertinoDatePickerMode.dateAndTime,
              use24hFormat: true,
              initialDateTime: value,
              onDateTimeChanged: onChanged,
            ),
          ),
      ],
    );
  }

  Widget _scheduleSection() {
    return GatheringSectionCard(
      title: widget.copy.scheduleSection,
      child: Column(
        children: <Widget>[
          _dateTimeField(
            key: GatheringCreatePage.startAtFieldKey,
            label: widget.copy.startAtLabel,
            slot: _GatheringDatePickerSlot.startAt,
            value: _startAt,
            onChanged: (value) => setState(() {
              _startAt = value;
              if (!_endAt.isAfter(_startAt)) {
                _endAt = _startAt.add(const Duration(hours: 2));
              }
            }),
          ),
          _gap(),
          _dateTimeField(
            key: GatheringCreatePage.endAtFieldKey,
            label: widget.copy.endAtLabel,
            slot: _GatheringDatePickerSlot.endAt,
            value: _endAt,
            onChanged: (value) => setState(() => _endAt = value),
          ),
          _gap(),
          _admissionClosesField(),
        ],
      ),
    );
  }

  Widget _admissionClosesField() {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final admissionClosesAt = _admissionClosesAt;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          toggled: admissionClosesAt != null,
          label: widget.copy.admissionClosesAtLabel,
          child: Row(
            children: <Widget>[
              Expanded(
                child: Text(
                  widget.copy.admissionClosesAtLabel,
                  style: TextStyle(
                    color: foreground,
                    fontSize: AppTypography.base,
                  ),
                ),
              ),
              CupertinoSwitch(
                key: GatheringCreatePage.admissionClosesFieldKey,
                value: admissionClosesAt != null,
                onChanged: (enabled) => setState(() {
                  _admissionClosesAt = enabled
                      ? _startAt.subtract(const Duration(hours: 1))
                      : null;
                  if (!enabled &&
                      _expandedPicker ==
                          _GatheringDatePickerSlot.admissionClosesAt) {
                    _expandedPicker = _GatheringDatePickerSlot.none;
                  }
                }),
              ),
            ],
          ),
        ),
        if (admissionClosesAt != null) ...<Widget>[
          _gap(),
          _dateTimeField(
            key: const ValueKey<String>(
              'gathering-create-admission-closes-at-picker',
            ),
            label: widget.copy.admissionClosesAtLabel,
            slot: _GatheringDatePickerSlot.admissionClosesAt,
            value: admissionClosesAt,
            onChanged: (value) => setState(() => _admissionClosesAt = value),
          ),
        ],
      ],
    );
  }

  Widget _placeSection() {
    return GatheringSectionCard(
      title: widget.copy.placeSection,
      child: Column(
        children: <Widget>[
          GatheringChoiceField<GatheringPlaceMode>(
            label: widget.copy.placeModeLabel,
            value: _placeMode,
            choices: GatheringPlaceMode.values
                .map(
                  (value) => GatheringChoice<GatheringPlaceMode>(
                    value: value,
                    label: widget.copy.placeMode(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _placeMode = value),
          ),
          _gap(),
          GatheringLabeledTextField(
            label: widget.copy.coarsePlaceLabel,
            controller: _coarsePlaceController,
            placeholder: widget.copy.coarsePlaceLabel,
          ),
          _gap(),
          GatheringLabeledTextField(
            label: widget.copy.exactMeetingPointLabel,
            controller: _exactMeetingPointController,
            placeholder: widget.copy.exactMeetingPointLabel,
          ),
          _gap(),
          GatheringLabeledTextField(
            label: widget.copy.onlineLocationLabel,
            controller: _onlineLocationController,
            placeholder: widget.copy.onlineLocationLabel,
          ),
        ],
      ),
    );
  }

  Widget _policySection() {
    return GatheringSectionCard(
      title: widget.copy.policySection,
      child: Column(
        children: <Widget>[
          GatheringChoiceField<GatheringAudiencePolicy>(
            label: widget.copy.audienceLabel,
            value: _audience,
            choices: GatheringAudiencePolicy.values
                .map(
                  (value) => GatheringChoice<GatheringAudiencePolicy>(
                    value: value,
                    label: widget.copy.audience(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _audience = value),
          ),
          _gap(),
          GatheringChoiceField<GatheringAdmissionPolicy>(
            label: widget.copy.admissionLabel,
            value: _admission,
            choices: GatheringAdmissionPolicy.values
                .map(
                  (value) => GatheringChoice<GatheringAdmissionPolicy>(
                    value: value,
                    label: widget.copy.admission(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _admission = value),
          ),
          _gap(),
          GatheringLabeledTextField(
            label: widget.copy.capacityLabel,
            controller: _capacityController,
            placeholder: widget.copy.capacityLabel,
            keyboardType: TextInputType.number,
          ),
          _gap(),
          GatheringChoiceField<GatheringTimeDisclosure>(
            label: widget.copy.timeDisclosureLabel,
            value: _timeDisclosure,
            choices: GatheringTimeDisclosure.values
                .map(
                  (value) => GatheringChoice<GatheringTimeDisclosure>(
                    value: value,
                    label: widget.copy.timeDisclosure(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _timeDisclosure = value),
          ),
          _gap(),
          GatheringChoiceField<GatheringPlaceDisclosure>(
            label: widget.copy.placeDisclosureLabel,
            value: _placeDisclosure,
            choices: GatheringPlaceDisclosure.values
                .map(
                  (value) => GatheringChoice<GatheringPlaceDisclosure>(
                    value: value,
                    label: widget.copy.placeDisclosure(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _placeDisclosure = value),
          ),
          _gap(),
          GatheringChoiceField<GatheringRosterDisclosure>(
            label: widget.copy.rosterDisclosureLabel,
            value: _rosterDisclosure,
            choices: GatheringRosterDisclosure.values
                .map(
                  (value) => GatheringChoice<GatheringRosterDisclosure>(
                    value: value,
                    label: widget.copy.rosterDisclosure(value),
                  ),
                )
                .toList(growable: false),
            onChanged: (value) => setState(() => _rosterDisclosure = value),
          ),
          _gap(),
          _creatorParticipatesField(),
        ],
      ),
    );
  }

  Widget _creatorParticipatesField() {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    return Semantics(
      toggled: _creatorParticipates,
      label: widget.copy.creatorParticipatesLabel,
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              widget.copy.creatorParticipatesLabel,
              style: TextStyle(
                color: foreground,
                fontSize: AppTypography.base,
              ),
            ),
          ),
          CupertinoSwitch(
            value: _creatorParticipates,
            onChanged: (value) => setState(() => _creatorParticipates = value),
          ),
        ],
      ),
    );
  }

  Widget _submissionStatus() {
    final error = _submissionError;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Semantics(
          liveRegion: true,
          label: _stepLabel(),
          child: Text(
            _stepLabel(),
            key: GatheringCreatePage.statusKey,
            style: TextStyle(
              color: AppColors.primaryColor,
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
            ),
          ),
        ),
        if (_validationFailed) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            widget.copy.invalidFormMessage,
            style: TextStyle(
              color: AppColors.error,
              fontSize: AppTypography.sm,
            ),
          ),
        ],
        if (error != null) ...<Widget>[
          SizedBox(height: AppSpacing.intraGroupSm),
          AppSectionErrorCard(
            semantic: ensureRetryUiErrorSemantic(
              runtimeErrorSemantic(
                context,
                error: error,
                category: UiErrorCategory.submit,
                scope: UiErrorScope.form,
              ),
              retryLabel: widget.copy.retryAction,
            ),
            margin: EdgeInsets.zero,
            onAction: (_) async => _submit(),
          ),
        ],
      ],
    );
  }
}
