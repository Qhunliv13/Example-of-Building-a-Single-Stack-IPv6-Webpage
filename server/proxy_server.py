import asyncio, logging, websockets

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("proxy")

GPU_WS = "ws://127.0.0.1:8082/ws"
WS_PORT = 8766

async def handler(ws):
    try:
        async with websockets.connect(GPU_WS, max_size=50*1024*1024) as gpu:
            log.info("Connected to GPUStream")
            first = True
            async for msg in gpu:
                if isinstance(msg, bytes):
                    if first:
                        msg = bytearray(msg)
                        if len(msg) > 4:
                            msg[3] = 41  # level 4.1 in AVCC header
                            # Also patch SPS level (SPS is at offset 8: NALtype(1)+profile(1)+constraints(1)+level(1)=4 bytes)
                            if len(msg) > 12:
                                msg[11] = 41  # SPS level
                        msg = bytes(msg)
                        first = False
                    await ws.send(msg)
    except Exception as e:
        log.error(f"{e}")

async def main():
    async with websockets.serve(handler, "0.0.0.0", WS_PORT, ping_interval=30, ping_timeout=10, max_size=50*1024*1024):
        log.info(f"Raw H.264 proxy on {WS_PORT}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
