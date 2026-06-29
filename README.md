# IPv6 Remote Desktop with Cloudflare Tunnel IPv4 Fallback

Demonstrates how to:
1. Expose a service over **IPv6 only** (no public IPv4)
2. Supplement with **Cloudflare Tunnel** to provide IPv4 access
3. Bypass CGNAT without buying a VPS

## Architecture

```
IPv6 clients ──→ AAAA record ──→ direct IPv6 connection to your server
IPv4 clients ──→ CNAME record  ──→ Cloudflare Tunnel ──→ your server
```

### Service Pipeline

```
GPUStream (NVENC H.264, :8082) → proxy_server.py (:8766) → viewer_h264.html (WebCodecs)
ScreenStream (MJPEG, :8081)    → server.py (:8765)        → viewer.html (Canvas+Audio)
WASAPI Loopback (C)            → audio_server.py (:8767)   → viewer.html
```

## Files

| File | Purpose |
|------|---------|
| `server/proxy_server.py` | H.264 NVENC passthrough → WebSocket |
| `server/server.py` | MJPEG bridge → WebSocket |
| `server/audio_server.py` | WASAPI system audio → WebSocket |
| `capture/wasapi_loopback.c` | WASAPI loopback audio capture (C) |
| `web/viewer_h264.html` | H.264 WebCodecs viewer |
| `web/viewer.html` | MJPEG + audio viewer |
| `config/nginx.conf` | nginx config (static files + WebSocket proxies) |
| `tunnel/config.yml` | Cloudflare Tunnel ingress rules |

## Network Setup

### DNS (Cloudflare)

| Type | Name | Target | Proxy |
|------|------|--------|-------|
| AAAA | `direct.yourdomain.com` | `2409:...` (your IPv6) | DNS-only |
| CNAME | `service.yourdomain.com` | Tunnel CNAME | DNS-only |

### Cloudflare Tunnel

```bash
cloudflared tunnel create my-tunnel
cloudflared tunnel route dns my-tunnel service.yourdomain.com
cloudflared tunnel run my-tunnel
```

All traffic goes through:
- IPv6: Direct, full bandwidth
- IPv4: Via Cloudflare Tunnel (encrypted QUIC/HTTP2)

## Requirements

- Windows 10+, NVIDIA GPU (NVENC)
- Python 3.13+, nginx
- MinGW (for compiling wasapi_loopback.c)
- Cloudflare-managed domain
- IPv6 from ISP (no public IPv4 needed)

## Contact

xi_qhunliv13@outlook.com | Bilibili UID:2001466201
