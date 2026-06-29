#include <windows.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <stdio.h>
#include <fcntl.h>
#include <io.h>

#define REFTIMES_PER_SEC 10000000
#define REFTIMES_PER_MILLISEC 10000

int main() {
    HRESULT hr;
    IMMDeviceEnumerator *pEnumerator = NULL;
    IMMDevice *pDevice = NULL;
    IAudioClient *pAudioClient = NULL;
    IAudioCaptureClient *pCaptureClient = NULL;
    WAVEFORMATEX *pwfx = NULL;
    UINT32 bufferFrameCount;
    UINT32 numFramesAvailable;
    UINT32 packetLength = 0;
    BYTE *pData = NULL;
    DWORD flags;
    
    // Initialize COM
    CoInitializeEx(NULL, COINIT_MULTITHREADED);
    
    // Get enumerator
    hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), NULL,
                          CLSCTX_ALL, __uuidof(IMMDeviceEnumerator),
                          (void**)&pEnumerator);
    if (FAILED(hr)) { fprintf(stderr, "CoCreateInstance failed\n"); return 1; }
    
    // Get default render device
    hr = pEnumerator->GetDefaultAudioEndpoint(eRender, eConsole, &pDevice);
    if (FAILED(hr)) { fprintf(stderr, "GetDefaultAudioEndpoint failed\n"); return 1; }
    
    // Activate audio client
    hr = pDevice->Activate(__uuidof(IAudioClient), CLSCTX_ALL, NULL,
                           (void**)&pAudioClient);
    if (FAILED(hr)) { fprintf(stderr, "Activate failed\n"); return 1; }
    
    // Get mix format
    hr = pAudioClient->GetMixFormat(&pwfx);
    if (FAILED(hr)) { fprintf(stderr, "GetMixFormat failed\n"); return 1; }
    
    // Initialize in loopback mode
    hr = pAudioClient->Initialize(AUDCLNT_SHAREMODE_SHARED,
                                   AUDCLNT_STREAMFLAGS_LOOPBACK,
                                   REFTIMES_PER_SEC, 0, pwfx, NULL);
    if (FAILED(hr)) { fprintf(stderr, "Initialize failed: %08X\n", hr); return 1; }
    
    // Get capture client
    hr = pAudioClient->GetService(__uuidof(IAudioCaptureClient),
                                   (void**)&pCaptureClient);
    if (FAILED(hr)) { fprintf(stderr, "GetService failed\n"); return 1; }
    
    hr = pAudioClient->GetBufferSize(&bufferFrameCount);
    if (FAILED(hr)) { fprintf(stderr, "GetBufferSize failed\n"); return 1; }
    
    // Set stdout to binary mode
    _setmode(_fileno(stdout), _O_BINARY);
    
    // Output format header: sample rate as uint32 little-endian
    UINT32 sampleRate = pwfx->nSamplesPerSec;
    fwrite(&sampleRate, 4, 1, stdout);
    fflush(stdout);
    
    // Start capture
    hr = pAudioClient->Start();
    if (FAILED(hr)) { fprintf(stderr, "Start failed\n"); return 1; }
    
    while (TRUE) {
        Sleep(10);  // 10ms polling
        
        hr = pCaptureClient->GetNextPacketSize(&packetLength);
        if (FAILED(hr)) break;
        
        while (packetLength != 0) {
            hr = pCaptureClient->GetBuffer(&pData, &numFramesAvailable, &flags, NULL, NULL);
            if (FAILED(hr)) break;
            
            if (flags & AUDCLNT_BUFFERFLAGS_SILENT) {
                static const short zero = 0;
                for (UINT32 i = 0; i < numFramesAvailable; i++)
                    fwrite(&zero, 2, 1, stdout);
            } else {
                UINT32 frames = numFramesAvailable;
                float *src = (float*)pData;
                // Batch convert to int16
                static short *buf = NULL;
                static UINT32 bufSize = 0;
                if (bufSize < frames) {
                    if (buf) free(buf);
                    buf = (short*)malloc(frames * 2);
                    bufSize = frames;
                }
                for (UINT32 i = 0; i < frames; i++) {
                    float sample = src[i * pwfx->nChannels];
                    buf[i] = (short)(sample * 32767);
                }
                fwrite(buf, 2, frames, stdout);
            }
            fflush(stdout);
            
            hr = pCaptureClient->ReleaseBuffer(numFramesAvailable);
            if (FAILED(hr)) break;
            
            hr = pCaptureClient->GetNextPacketSize(&packetLength);
            if (FAILED(hr)) break;
        }
    }
    
    pAudioClient->Stop();
    pCaptureClient->Release();
    pAudioClient->Release();
    pDevice->Release();
    pEnumerator->Release();
    CoUninitialize();
    return 0;
}
