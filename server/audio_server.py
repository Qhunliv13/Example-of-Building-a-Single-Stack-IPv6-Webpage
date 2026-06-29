import asyncio, json, logging, subprocess, struct, array

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                    filename=r"C:\web\build\audio_server.log", filemode="w")
log = logging.getLogger("audio")
WS_PORT = 8767
WASAPI_EXE = r"C:\web\build\wasapi_loopback.exe"

SAMPLE_RATE = 48000
clients = set()
SEND_CHUNK = 4096

def reduce_gain(data):
    vals = array.array('h', data)
    for i in range(len(vals)):
        v = int(vals[i] * 0.3)
        if v > 32767: v = 32767
        if v < -32768: v = -32768
        vals[i] = v
    return vals.tobytes()

async def pcm_reader():
    global SAMPLE_RATE, clients
    while True:
        try:
            proc = await asyncio.create_subprocess_exec(
                WASAPI_EXE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            header = await proc.stdout.readexactly(4)
            SAMPLE_RATE = struct.unpack('<I', header)[0]
            log.info(f"Captured at {SAMPLE_RATE} Hz")

            while True:
                data = await proc.stdout.read(4096)
                if not data: break
                data = reduce_gain(data)
                dead = set()
                for ws in list(clients):
                    try: await ws.send(data)
                    except: dead.add(ws)
                clients -= dead

            err = await proc.stderr.read()
            if err: log.warning(f"wasapi stderr: {err.decode(errors='replace')}")
            await proc.wait()
            log.warning("Restarting WASAPI capture...")
        except Exception as e:
            log.error(f"reader: {e}")
            await asyncio.sleep(2)

async def handler(ws):
    clients.add(ws)
    await ws.send(json.dumps({"type":"info","encoder":"pcm","rate":SAMPLE_RATE,"channels":1}))
    try:
        async for _ in ws:  # keep alive, wait for client close
            pass
    except:
        pass
    finally:
        clients.discard(ws)

async def main():
    import websockets
    asyncio.create_task(pcm_reader())
    log.info(f"Audio server 0.0.0.0:{WS_PORT}")
    async with websockets.serve(handler, "0.0.0.0", WS_PORT, ping_interval=30, ping_timeout=10):
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
