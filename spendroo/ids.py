"""
Row identifiers.

UUIDv7 (RFC 9562): a 48-bit millisecond timestamp followed by random bits, so
ids sort roughly by creation time and index well. Clients make the same kind
of id offline; Python gains uuid.uuid7 only in 3.14.
"""
import os
import time
import uuid


def uuid7():
    millis = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), 'big')  # 80 random bits, 74 used
    value = (millis & 0xFFFF_FFFF_FFFF) << 80   # unix_ts_ms
    value |= 0x7 << 76                          # version
    value |= ((rand >> 62) & 0xFFF) << 64       # rand_a
    value |= 0b10 << 62                         # variant
    value |= rand & ((1 << 62) - 1)             # rand_b
    return uuid.UUID(int=value)
