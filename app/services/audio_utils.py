import struct
import math

BIAS = 132
CLIP = 32635

_seg_end = [0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF, 0x3FFF, 0x7FFF]

def _search(val):
    for i in range(8):
        if val <= _seg_end[i]:
            return i
    return 8

def _linear2ulaw_calc(pcm_val):
    if pcm_val < 0:
        pcm_val = -pcm_val
        mask = 0x7F
    else:
        mask = 0xFF
        
    if pcm_val > CLIP:
        pcm_val = CLIP
    pcm_val += BIAS
    
    seg = _search(pcm_val)
    if seg >= 8:
        return 0x7F ^ mask
    else:
        uval = (seg << 4) | ((pcm_val >> (seg + 3)) & 0xF)
        return uval ^ mask

def _ulaw2linear_calc(u_val):
    u_val = ~u_val & 0xFF
    t = ((u_val & 0x0F) << 3) + BIAS
    exponent = (u_val & 0x70) >> 4
    t <<= exponent
    
    if u_val & 0x80:
        return BIAS - t
    else:
        return t - BIAS

# Precompute G.711 lookup tables for maximum runtime performance
MULAW_TO_PCM = [0] * 256
for b in range(256):
    MULAW_TO_PCM[b] = _ulaw2linear_calc(b)

PCM_TO_MULAW = [0] * 65536
for p in range(-32768, 32768):
    PCM_TO_MULAW[p + 32768] = _linear2ulaw_calc(p)


class MuLawSpeechEnhancer:
    """Stateful low-cost inbound phone speech cleanup for 20 ms PCMU frames.

    Removes low-frequency rumble, gates steady background noise between words,
    and gently raises quiet speech before it reaches Realtime transcription.
    """
    def __init__(self, target_rms: float = 2200.0, max_gain: float = 2.8,
                 noise_gate_rms: float = 170.0, sample_rate: int = 8000):
        self.target_rms = target_rms
        self.max_gain = max(1.0, max_gain)
        self.noise_gate_rms = noise_gate_rms
        self.gain = 1.0
        self.previous_input = 0.0
        self.previous_output = 0.0
        rc = 1.0 / (2.0 * math.pi * 110.0)
        dt = 1.0 / sample_rate
        self.highpass_alpha = rc / (rc + dt)

    def process(self, ulaw_bytes: bytes) -> bytes:
        if not ulaw_bytes:
            return ulaw_bytes
        filtered = []
        for byte in ulaw_bytes:
            sample = float(MULAW_TO_PCM[byte])
            highpassed = self.highpass_alpha * (
                self.previous_output + sample - self.previous_input
            )
            self.previous_input, self.previous_output = sample, highpassed
            filtered.append(highpassed)
        rms = math.sqrt(sum(sample * sample for sample in filtered) / len(filtered))
        if rms < self.noise_gate_rms:
            desired_gain = 0.28
        else:
            desired_gain = min(self.max_gain, max(1.0, self.target_rms / max(rms, 1.0)))
        smoothing = 0.20 if desired_gain > self.gain else 0.45
        self.gain += (desired_gain - self.gain) * smoothing
        output = bytearray(len(filtered))
        for index, sample in enumerate(filtered):
            value = int(max(-28000, min(28000, sample * self.gain)))
            output[index] = PCM_TO_MULAW[value + 32768]
        return bytes(output)

def ulaw2pcm(ulaw_bytes: bytes) -> bytes:
    """Converts 8-bit mu-law bytes to signed 16-bit little-endian PCM bytes."""
    samples = [MULAW_TO_PCM[b] for b in ulaw_bytes]
    return struct.pack(f"<{len(samples)}h", *samples)

def pcm2ulaw(pcm_bytes: bytes) -> bytes:
    """Converts signed 16-bit little-endian PCM bytes to 8-bit mu-law bytes."""
    num_samples = len(pcm_bytes) // 2
    if num_samples == 0:
        return b""
    samples = struct.unpack(f"<{num_samples}h", pcm_bytes)
    out = [PCM_TO_MULAW[s + 32768] for s in samples]
    return bytes(out)

def resample_8k_to_16k(pcm16_data: bytes) -> bytes:
    """Upsamples 16-bit linear PCM from 8kHz to 16kHz using linear interpolation."""
    num_samples = len(pcm16_data) // 2
    if num_samples <= 1:
        return pcm16_data + pcm16_data
    
    samples = struct.unpack(f"<{num_samples}h", pcm16_data)
    resampled = []
    for i in range(num_samples - 1):
        s1 = samples[i]
        s2 = samples[i+1]
        resampled.append(s1)
        resampled.append((s1 + s2) // 2)
    
    # Append the last sample duplicated to complete the block
    resampled.append(samples[-1])
    resampled.append(samples[-1])
    return struct.pack(f"<{len(resampled)}h", *resampled)

def resample_16k_to_8k(pcm16_data: bytes) -> bytes:
    """Downsamples 16-bit linear PCM from 16kHz to 8kHz by decimation."""
    num_samples = len(pcm16_data) // 2
    if num_samples <= 1:
        return pcm16_data
    
    samples = struct.unpack(f"<{num_samples}h", pcm16_data)
    downsampled = samples[::2]
    return struct.pack(f"<{len(downsampled)}h", *downsampled)

def wav_to_raw_pcm(wav_bytes: bytes) -> bytes:
    """Strips RIFF/WAV header to return the raw data subchunk bytes."""
    if not wav_bytes.startswith(b"RIFF"):
        return wav_bytes
    
    idx = wav_bytes.find(b"data")
    if idx == -1:
        return wav_bytes[44:]
    
    try:
        data_size = struct.unpack("<I", wav_bytes[idx+4:idx+8])[0]
        return wav_bytes[idx+8 : idx+8+data_size]
    except Exception:
        return wav_bytes[44:]

def calculate_rms(pcm_data: bytes) -> float:
    """Calculates the root mean square (RMS) amplitude of 16-bit linear PCM audio."""
    import math
    num_samples = len(pcm_data) // 2
    if num_samples == 0:
        return 0.0
    samples = struct.unpack(f"<{num_samples}h", pcm_data)
    sum_squares = sum(s * s for s in samples)
    return math.sqrt(sum_squares / num_samples)

def get_wav_sample_rate(wav_bytes: bytes) -> int:
    """Extracts the sample rate from WAV bytes. Defaults to 16000 if not a valid WAV or parsing fails."""
    if not wav_bytes.startswith(b"RIFF"):
        return 16000
    try:
        # Sample rate is a 32-bit unsigned integer at offset 24
        return struct.unpack("<I", wav_bytes[24:28])[0]
    except Exception:
        return 16000

def resample_pcm(pcm16_data: bytes, orig_sr: int, target_sr: int = 8000) -> bytes:
    """
    Resamples 16-bit linear PCM from orig_sr to target_sr using fast linear interpolation.
    This is highly optimized for real-time telephony responses (latency under 10ms).
    """
    if orig_sr == target_sr:
        return pcm16_data
        
    num_samples = len(pcm16_data) // 2
    if num_samples <= 1:
        return pcm16_data
        
    samples = struct.unpack(f"<{num_samples}h", pcm16_data)
    
    # Calculate the number of output samples
    ratio = target_sr / orig_sr
    num_out_samples = int(num_samples * ratio)
    if num_out_samples <= 1:
        return pcm16_data
        
    out_samples = []
    for i in range(num_out_samples):
        orig_idx = i / ratio
        idx = int(orig_idx)
        frac = orig_idx - idx
        
        if idx >= num_samples - 1:
            val = samples[-1]
        else:
            s1 = samples[idx]
            s2 = samples[idx + 1]
            val = int(round(s1 + frac * (s2 - s1)))
            
        # Clip to signed 16-bit range
        if val > 32767:
            val = 32767
        elif val < -32768:
            val = -32768
            
        out_samples.append(val)
        
    return struct.pack(f"<{len(out_samples)}h", *out_samples)
