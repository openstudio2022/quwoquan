# Voice Message T4 Evidence

## Scope

- Story: `chat-conversation/list-detail-message-delivery/voice-message`
- Goal: validate the commercial-readiness journey for chat voice input, send, recovery, playback, and comment ASR exclusion.
- Date: 2026-06-06

## Automated Evidence

- `quwoquan_app/test/components/input/customizable_chat_input_bar_test.dart`
  - Voice entry is opt-in.
  - Hold-to-talk starts recording UI.
  - Release delegates to the recording callback without creating a text/ASR payload.
  - Slide-up cancel does not send.
  - Real amplitude stream drives the waveform HUD.
  - Recording HUD shows elapsed time.
- `quwoquan_app/test/ui/chat/providers/voice_send_provider_test.dart`
  - Completed upload sends `type=audio` with `media` payload.
  - Invalid recording does not upload or send.
  - Upload failure maps to unified voice upload copy.
  - Message send failure is not misreported as completed.
  - Upload/send funnel events are emitted.
- `quwoquan_app/test/ui/chat/providers/voice_offline_queue_test.dart`
  - Queued voice item is deleted only after successful drain.
  - Failed drain keeps the queued item for later recovery.
- `quwoquan_app/test/ui/chat/providers/voice_player_manager_test.dart`
  - Empty URL produces a unified unavailable playback state.
  - Switching voice messages stops the previous backend and binds the new source.
  - Backend playback failure is surfaced through the unified unavailable state.
- `quwoquan_app/test/ui/chat/widgets/chat_message_bubble_widget_test.dart`
  - Audio bubble renders duration width.
  - Recalled audio no longer shows playback.
  - Empty media URL stays non-playable.
- `quwoquan_app/test/components/comment_system/comment_input_overlay_test.dart`
  - Comment input overlay does not expose mic, voice, or ASR entry.
- `quwoquan_app/test/components/comment_system/comment_viewer_modal_widget_test.dart`
  - Comment modal and immersive split sheet keep comment input without voice entry.

## Device Journey Checklist

The following checks are required before release candidate sign-off on physical iOS/Android devices:

- Grant microphone permission, record a valid voice message, release to send, confirm the audio bubble appears and can be played.
- Deny microphone permission once and permanently; verify the temporary denial copy and the settings action.
- Record shorter than the minimum duration; verify no upload or message send occurs.
- Record until the maximum duration; verify auto-stop and send.
- Toggle airplane mode after recording; verify the item enters the pending queue and is retried after network recovery.
- Tap a second voice bubble while the first is playing; verify only one active playback.
- Open comments, replies, article inline comments, and immersive comments; verify no mic, ASR, or audio-comment entry appears.

## Release Notes

- Current automated coverage closes T1/T2 evidence for core interaction, media payload, failure handling, offline queue semantics, playback state, and comment exclusion.
- Physical device checks remain mandatory for microphone OS prompts, real audio capture, weak network timing, and platform audio-session behavior.
