part of 'chat_conversation_page.dart';

extension _ChatConversationPageSelectionActions
    on _ChatConversationPageActionsState {
  void _toggleSelect(String id) {
    _updateSelection(() {
      if (_selectedIds.contains(id)) {
        _selectedIds.remove(id);
      } else {
        _selectedIds.add(id);
      }
    });
  }

  void _cancelSelection() {
    _updateSelection(() {
      _isSelectionMode = false;
      _selectedIds.clear();
    });
  }
}
