"""One-time developer tool: build models/orb_match_fp16.onnx.

Brute-force Hamming matching of ORB descriptors on the GPU (DirectML), used by
the crop-verification stage. It gives the same matches as OpenCV's
BFMatcher(NORM_HAMMING).knnMatch(k=2) followed by the ratio test.

Inputs for a batch of P image pairs (descriptors padded to N rows / M keys):
    DA [P, N, 32] uint8    ORB descriptors of image A
    DB [P, M, 32] uint8    ORB descriptors of image B
    MB [P, 1, M]  fp16     0 for real keys of B, -30000 for padding

Each 256-bit descriptor is unpacked on the GPU (lookup table) to +1/-1 values,
so hamming(a, b) = (256 - a.b) / 2 and the best match is the largest dot
product. Outputs, per descriptor of A:
    J1  index of the best key of B
    V1  best dot product
    V2  best dot product among keys that are not tied with V1
    CNT number of keys tied with V1 (>= 2 means the second best equals the best)

TopK is avoided on purpose: on DirectML it is ~10x slower than these reductions.
All values are small integers, so fp16 is exact. Needs only `pip install onnx`.
"""

import os

import numpy as np
import onnx
import onnx.helper as h
from onnx import TensorProto as T
from onnx import numpy_helper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build():
    lut = np.unpackbits(np.arange(256, dtype=np.uint8)[:, None], axis=1).astype(np.float16) * 2 - 1
    nodes = [
        # unpack: [P, N, 32] uint8 -> [P, N, 32, 8] -> [P, N, 256]
        h.make_node("Cast", ["DA"], ["DAi"], to=T.INT64),
        h.make_node("Gather", ["LUT", "DAi"], ["A4"], axis=0),
        h.make_node("Reshape", ["A4", "shape256"], ["A"]),
        h.make_node("Cast", ["DB"], ["DBi"], to=T.INT64),
        h.make_node("Gather", ["LUT", "DBi"], ["B4"], axis=0),
        h.make_node("Reshape", ["B4", "shape256"], ["B"]),
        h.make_node("Transpose", ["B"], ["BT"], perm=[0, 2, 1]),
        # scores
        h.make_node("MatMul", ["A", "BT"], ["S"]),
        h.make_node("Add", ["S", "MB"], ["S2"]),
        # best, ties at best, second best
        h.make_node("ArgMax", ["S2"], ["J1"], axis=-1, keepdims=1),
        h.make_node("ReduceMax", ["S2", "axl"], ["V1"], keepdims=1),
        h.make_node("Equal", ["S2", "V1"], ["EQ"]),
        h.make_node("Cast", ["EQ"], ["EQf"], to=T.FLOAT16),
        h.make_node("ReduceSum", ["EQf", "axl"], ["CNT"], keepdims=1),
        h.make_node("Mul", ["EQf", "big"], ["PEN"]),
        h.make_node("Sub", ["S2", "PEN"], ["S3"]),
        h.make_node("ReduceMax", ["S3", "axl"], ["V2"], keepdims=1),
    ]
    inits = [
        numpy_helper.from_array(lut, "LUT"),
        h.make_tensor("shape256", T.INT64, [3], [0, 0, 256]),
        h.make_tensor("axl", T.INT64, [1], [-1]),
        h.make_tensor("big", T.FLOAT16, [], [30000.0]),
    ]
    inputs = [
        h.make_tensor_value_info("DA", T.UINT8, ["p", "n", 32]),
        h.make_tensor_value_info("DB", T.UINT8, ["p", "m", 32]),
        h.make_tensor_value_info("MB", T.FLOAT16, ["p", 1, "m"]),
    ]
    outputs = [
        h.make_tensor_value_info("J1", T.INT64, ["p", "n", 1]),
        h.make_tensor_value_info("V1", T.FLOAT16, ["p", "n", 1]),
        h.make_tensor_value_info("V2", T.FLOAT16, ["p", "n", 1]),
        h.make_tensor_value_info("CNT", T.FLOAT16, ["p", "n", 1]),
    ]
    g = h.make_graph(nodes, "orb_match_top2", inputs, outputs, initializer=inits)
    m = h.make_model(g, opset_imports=[h.make_opsetid("", 18)])
    m.ir_version = 9
    onnx.checker.check_model(m)
    return m


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    path = os.path.join(ROOT, "models", "orb_match_fp16.onnx")
    onnx.save(build(), path)
    print("saved", path)
