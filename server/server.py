"""
Bridge: ScreenStream MJPEG → WebSocket. Simple queue, no rate limit.
"""
import asyncio, json, logging, time, websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bridge")

MJPEG_URL = "http://127.0.0.1:8081/stream"
WS_PORT = 8765
SKIP = 2

import struct

def get_jpeg_size(jpeg):
    pos = jpeg.find(b"\xff\xc0")
    if pos >= 0 and pos + 9 < len(jpeg):
        h = struct.unpack(">H", jpeg[pos+5:pos+7])[0]
        w = struct.unpack(">H", jpeg[pos+7:pos+9])[0]
        return w, h
    return 0, 0

async def mjpeg_reader(queue):
    import httpx
    frame = 0
    last_w = 0
    while True:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", MJPEG_URL) as resp:
                    buf = b""
                    async for chunk in resp.aiter_bytes():
                        buf += chunk
                        while True:
                            cl = buf.find(b"Content-Length: ")
                            if cl < 0: break
                            ce = buf.find(b"\r\n", cl)
                            if ce < 0: break
                            n = int(buf[cl + 16:ce])
                            he = buf.find(b"\r\n\r\n", ce)
                            if he < 0: break
                            js = he + 4
                            if len(buf) < js + n: break
                            jpeg = buf[js:js + n]
                            buf = buf[js + n:]
                            frame += 1
                            if frame % SKIP != 0: continue
                            # Check resolution
                            w, h = get_jpeg_size(jpeg)
                            if w > 0 and (w != last_w):
                                last_w = w
                                try:
                                    queue.put_nowait(("res", w, h))
                                except asyncio.QueueFull: pass
                            try:
                                queue.put_nowait(("jpg", jpeg))
                            except asyncio.QueueFull:
                                pass
        except Exception as e:
            log.error(f"reader: {e}")
            await asyncio.sleep(2)

async def handler(ws):
    queue = asyncio.Queue(maxsize=10)
    asyncio.create_task(mjpeg_reader(queue))
    await ws.send(json.dumps({"type":"info","encoder":"mjpeg","width":3840,"height":2160,"fps":30}))
    try:
        while True:
            msg = await asyncio.wait_for(queue.get(), timeout=60)
            if msg[0] == "res":
                _, w, h = msg
                await ws.send(json.dumps({"type":"res","w":w,"h":h}))
            else:
                await ws.send(msg[1])
    except:
        pass

async def main():
    log.info(f"Bridge 0.0.0.0:{WS_PORT}")
    async with websockets.serve(handler, "0.0.0.0", WS_PORT, ping_interval=30, ping_timeout=10, max_size=20*1024*1024):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
