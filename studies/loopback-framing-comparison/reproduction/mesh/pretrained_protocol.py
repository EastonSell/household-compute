"""Bounded little-endian float32 frames. No pickle or executable payloads."""
import json
import math
import struct

MAX_FRAME_BYTES = 2 * 1024 * 1024


def validate_tokens(tokens):
    if not isinstance(tokens, list) or not 1 <= len(tokens) <= 64:
        raise ValueError('tokens must be a list of 1..64 unpadded token IDs')
    if any(type(token) is not int or not 0 <= token < 49152 for token in tokens):
        raise ValueError('invalid token ID')
    return tokens


def _shape(shape):
    if not isinstance(shape, list) or not 1 <= len(shape) <= 3:
        raise ValueError('shape must have 1..3 dimensions')
    if any(type(size) is not int or not 1 <= size <= 49152 for size in shape):
        raise ValueError('invalid shape dimension')
    size = math.prod(shape) * 4
    if size > MAX_FRAME_BYTES - 256:
        raise ValueError('tensor exceeds frame budget')
    return size


def encode_frame(shape, payload):
    if _shape(shape) != len(payload):
        raise ValueError('payload length does not match shape')
    header = json.dumps({'shape': shape, 'dtype': '<f4'}, separators=(',', ':')).encode('ascii')
    return struct.pack('<I', len(header)) + header + payload


def decode_frame(frame):
    if not 4 <= len(frame) <= MAX_FRAME_BYTES:
        raise ValueError('invalid frame length')
    header_length, = struct.unpack('<I', frame[:4])
    if not 1 <= header_length <= 256 or len(frame) < 4 + header_length:
        raise ValueError('invalid frame header length')
    try:
        header = json.loads(frame[4:4 + header_length])
        if not isinstance(header, dict) or set(header) != {'shape', 'dtype'} or header['dtype'] != '<f4':
            raise ValueError('unsupported tensor header')
        payload = frame[4 + header_length:]
        if _shape(header['shape']) != len(payload):
            raise ValueError('payload length does not match shape')
        return header['shape'], payload
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError('invalid frame header') from error
