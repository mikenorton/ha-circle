# Meet Circle for Home Assistant

A custom Home Assistant integration for [Meet Circle](https://meetcircle.com/) parental control devices.

Circle does not offer a public API. This integration uses a reverse-engineered cloud API to provide control through Home Assistant.

## Features

Each Circle profile appears as a device in Home Assistant with the following entities:

| Entity | Type | Description |
|---|---|---|
| **Internet Access** | Switch | Pause / unpause internet for the profile |
| **Weekday Bedtime** | Sensor | Current weekday bedtime (e.g. "21:00" or "Disabled") |
| **Weekend Bedtime** | Sensor | Current weekend bedtime (e.g. "22:00" or "Disabled") |
| **Profile Mode** | Sensor | Current mode (Filter, Pause, etc.) |
| **Late Bedtime Reward** | Button | Send a 15-minute late bedtime extension |

## Installation via HACS

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner and select **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Click **Add**
5. Search for "Meet Circle" in HACS and install it
6. Restart Home Assistant

## Configuration

1. Go to **Settings > Integrations > Add Integration**
2. Search for **Meet Circle**
3. Enter:
   - **Email**: Your Circle account email
   - **Password**: Your Circle account password
   - **Device ID**: Your Circle device ID (see below)

### Finding your Device ID

The device ID is a UUID used by the Circle app. To find it, you can use a proxy tool like [Charles Proxy](https://www.charlesproxy.com/) to inspect traffic from the Circle iOS app. Look for the `appid` query parameter in any API call, or the `deviceid` field in the JWT token.

## How it works

- Authenticates via AWS Cognito using your Circle email/password
- Exchanges the Cognito token for a Circle API access token
- Polls the Circle cloud API every 5 minutes for profile data
- Sends commands (pause, unpause, bedtime reward) through the same API

## Disclaimer

This integration is not affiliated with or endorsed by Meet Circle. It relies on undocumented APIs that could change at any time. Use at your own risk.
