"""Constants for the Meet Circle integration."""

DOMAIN = "circle"

# Circle API endpoints
AUTH_HOST = "https://auth.meetcircle-blue.co"
API_HOST = "https://vc02.meetcircle-blue.co"

GRANT_ADMIN_URL = f"{AUTH_HOST}/api/v2/grant/admin"
QUERY_ALL_URL = f"{API_HOST}/api/QUERY/all"
BADGES_URL = f"{API_HOST}/api/v2/profiles/badges"
BEDTIMES_URL = f"{API_HOST}/api/v2/profiles/{{pid}}/bedtimes"
UPDATE_MODE_URL = f"{API_HOST}/api/UPDATE/users/user/mode"
ADD_EXTENSION_URL = f"{API_HOST}/api/ADD/users/user/extensions/offTimes/extension"

# AWS Cognito settings
COGNITO_USER_POOL_ID = "us-west-2_TiQsgtChT"
COGNITO_CLIENT_ID = "fd7ail96985e3p3omb792ko0f"
COGNITO_REGION = "us-west-2"

# Config entry keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_DEVICE_ID = "device_id"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"

# Defaults
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes in seconds
DEFAULT_LATE_BEDTIME_MINUTES = 15

# User-Agent to mimic the iOS app
USER_AGENT = "Circle-iOS / 2.34.0 2226 | Parent | Apple | iPhone16,1 | iOS 26.1 | Phone"
