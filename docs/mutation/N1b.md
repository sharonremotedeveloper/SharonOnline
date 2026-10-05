# Mutation table — N1b notification API

| mutant | invariant | killing test |
| :-- | :-- | :-- |
| Remove `user=request.user` from list/read filters | notification data is owner-only | `test_notification_list_is_paginated_and_owner_only`, `test_notification_read_and_read_all_are_owner_scoped` |
| Return every row instead of `in_app=True` | e-mail-only rows are not in the centre | `test_notification_list_is_paginated_and_owner_only` |
| Disable mandatory-kind validation | mandatory e-mail preferences cannot be muted | `test_unread_count_and_preferences_enforce_mandatory_kinds` |
| Serialize `email_last_error` for all users | provider detail is staff-only | `test_staff_can_see_error_code_but_regular_users_cannot` |
| Remove page pagination | list contract remains bounded and paginated | `test_notification_list_is_paginated_and_owner_only` |

Execution is pending the repaired Python runtime.
