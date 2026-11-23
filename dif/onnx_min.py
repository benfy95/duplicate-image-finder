"""Minimal ONNX protobuf patching, so the app needs no `onnx` package.

Only one operation is needed: add a large constant tensor (initializer) to the
graph of a template model. ModelProto.graph is field 7; GraphProto.initializer
is field 5; TensorProto has dims (1), data_type (2), name (8), raw_data (9).
"""

import numpy as np

_DTYPES = {np.dtype(np.float32): 1, np.dtype(np.float16): 10, np.dtype(np.int64): 7}


def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _read_varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def _find_field(buf, field):
    """(start_of_key, start_of_value, end) of the first length-delimited `field`."""
    i = 0
    while i < len(buf):
        start = i
        key, i = _read_varint(buf, i)
        f, wt = key >> 3, key & 7
        if wt == 0:
            _, i = _read_varint(buf, i)
        elif wt == 1:
            i += 8
        elif wt == 5:
            i += 4
        elif wt == 2:
            ln, i = _read_varint(buf, i)
            if f == field:
                return start, i, i + ln
            i += ln
        else:
            raise ValueError(f"unsupported wire type {wt}")
    raise ValueError(f"field {field} not found")


def add_initializer(model_bytes, name, array):
    """Return new model bytes with `array` added as initializer `name`.
    The big raw buffer is copied only once."""
    arr = np.ascontiguousarray(array)
    head = b"".join([_varint((1 << 3) | 0) + _varint(int(d)) for d in arr.shape])     # dims
    head += _varint((2 << 3) | 0) + _varint(_DTYPES[arr.dtype])                       # data_type
    nb = name.encode()
    head += _varint((8 << 3) | 2) + _varint(len(nb)) + nb                             # name
    raw = memoryview(arr).cast("B")
    raw_hdr = _varint((9 << 3) | 2) + _varint(raw.nbytes)                             # raw_data
    tensor_len = len(head) + len(raw_hdr) + raw.nbytes
    init_hdr = _varint((5 << 3) | 2) + _varint(tensor_len)

    g_key, g_val, g_end = _find_field(model_bytes, 7)
    graph = model_bytes[g_val:g_end]
    new_graph_len = len(graph) + len(init_hdr) + tensor_len
    return b"".join([
        model_bytes[:g_key], _varint((7 << 3) | 2), _varint(new_graph_len),
        graph, init_hdr, head, raw_hdr, raw,
        model_bytes[g_end:],
    ])
