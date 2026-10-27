# MediaMTX streaming server (Student B, B1)

MediaMTX receives the phone's camera and hands it to everyone else:

| Who | Protocol | URL |
|---|---|---|
| Phone publishes (video only) | WebRTC / WHIP | `http://LAN_IP:8889/live/whip` |
| Ingest worker reads | RTSP (TCP) | `rtsp://localhost:8554/live` |
| Dashboard Live page plays | WebRTC / WHEP | `http://LAN_IP:8889/live/whep` |
| Fallback player | HLS | `http://LAN_IP:8888/live/` |

Config: [`mediamtx.yml`](mediamtx.yml), mounted by `docker-compose.yml`.

## Setup on a new laptop or network

1. Find the laptop's Wi-Fi IP: `ipconfig` → "Wireless LAN adapter Wi-Fi" → IPv4 Address.
2. Put it in `.env` at the repo root: `LAN_IP=192.168.0.105`
3. Start or refresh the container: `docker compose up -d`
4. Firewall, once per laptop, in an **administrator** PowerShell from the repo root:
   `powershell -ExecutionPolicy Bypass -File infra\mediamtx\open-firewall.ps1`

Check: `docker logs va-mediamtx` shows `[WebRTC] started with listeners on :8889 (TCP/HTTP), :8189 (UDP/ICE)`.

Every time the network changes (home, university, demo room, hotspot): repeat steps 1–3.

## Test without the app

On the publish page, before clicking Publish, set **video codec = H264** and **audio = none**.
Chrome picks AV1 by default, and RTSP readers (VLC, OpenCV) then get no video (black screen).

- **Laptop webcam:** open `http://localhost:8889/live/publish` in Chrome, click Publish.
- **Phone browser:** Chrome only allows the camera on `https://` or `localhost`. On the phone open
  `chrome://flags/#unsafely-treat-insecure-origin-as-secure`, add `http://LAN_IP:8889`, Enable,
  Relaunch. Then open `http://LAN_IP:8889/live/publish` and click Publish.
- **Watch on the laptop:** VLC → Media → Open Network Stream → `rtsp://localhost:8554/live`,
  or in a browser `http://localhost:8889/live/`.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Phone page does not load | Not on the same Wi-Fi, wrong IP, or firewall script not run |
| Page loads, Publish spins then fails | `LAN_IP` wrong or old → fix `.env`, `docker compose up -d`; UDP 8189 blocked |
| "Camera not available" in phone browser | The Chrome flag above is missing |
| VLC plays sound or nothing, picture is black | Video was sent as AV1/VP9: pick H264 on the publish page (`docker logs va-mediamtx` shows the tracks) |
| VLC shows nothing | Nobody is publishing yet; check `docker logs va-mediamtx` for `is publishing to path 'live'` |
| Some university/guest Wi-Fi blocks phone-to-laptop traffic | Use the phone's hotspot and connect the laptop to it |
