# Error Code Catalogue (Synthetic Reference)

| Code | HTTP (API) | Raised when |
|---|---|---|
| INVALID_RATING_SYMBOL | 422 | Symbol is not on any supported scale, or is malformed or empty |
| RATING_SCALE_MISMATCH | 422 | Symbol is valid only on the other agency's scale |
| NOT_MAPPABLE | 422 | A status code (WR, WD, NR) was submitted for cross-agency mapping |
| ACTION_TYPE_MISMATCH | 422 | Action type does not match the direction of the rating change |
| FUTURE_EFFECTIVE_DATE | 422 | Effective date is after today |
| RATING_ALREADY_EXISTS | 422 | NEW action while an active rating exists for that agency |
| INVALID_OUTLOOK | 422 | Outlook value is not in the allowed list |
| WATCH_DIRECTION_REQUIRED | 422 | Watch submitted without a direction |
| OUTLOOK_REQUIRED | 422 | Watch removed without providing an outlook |
| NOT_APPLICABLE_FOR_STATUS | 422 | Outlook/watch on a defaulted rating or a status code |
| INVALID_DATE_RANGE | 400 | from_date is after to_date |
| DATE_RANGE_TOO_LARGE | 400 | History range is longer than 10 years |
| ISSUER_NOT_FOUND | 404 | Unknown issuer id |
| INVALID_AGENCY | 400 | Agency is not MOODYS, FITCH or NORTHBRIDGE |
| UNAUTHORIZED | 401 | Missing or invalid bearer token |
| FORBIDDEN | 403 | Token lacks the required scope (e.g. ratings:write) |

All API errors use the body `{"code": "<CODE>", "message": "<human readable>"}`.
