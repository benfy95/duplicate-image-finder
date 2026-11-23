"""One-time developer tool: build models/knn_fp16.onnx and models/knn_fp32.onnx.

Exact top-k similarity search for one block of query rows against all keys,
designed to stay fast on DirectML (whose TopK is slow on very wide rows):

    S  = Q @ KT                       [b, n]        (n padded to a multiple of C)
    M  = max over each C-wide chunk   [b, n/C]
    CI = top-k chunks by M            [b, k]
    G  = those k chunks of S          [b, k*C]
    V, J = top-k of G                 [b, k]

Exact: any of a row's k best scores lies in one of its k highest-max chunks.
Outputs V (scores), J (position inside G) and CI (chunk ids); the global index
is CI[row, J // C] * C + J % C.  Needs only `pip install onnx`.
"""

import os

import onnx
import onnx.helper as h
from onnx import TensorProto as T

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHUNK = 512


def build(dt):
    nodes = [
        h.make_node("MatMul", ["Q", "KT"], ["S"]),
        h.make_node("Reshape", ["S", "shape3"], ["S3"]),             # [b, nc, C]
        h.make_node("ReduceMax", ["S3", "ax2"], ["M"], keepdims=0),  # [b, nc]
        h.make_node("TopK", ["M", "k"], ["MV", "CI"], axis=1),        # [b, k]
        h.make_node("Unsqueeze", ["CI", "ax2"], ["CI3"]),             # [b, k, 1]
        h.make_node("Expand", ["CI3", "expand"], ["IDX"]),            # [b, k, C]
        h.make_node("GatherElements", ["S3", "IDX"], ["G"], axis=1),  # [b, k, C]
        h.make_node("Reshape", ["G", "shape2"], ["G2"]),             # [b, k*C]
        h.make_node("TopK", ["G2", "k"], ["V", "J"], axis=1),         # [b, k]
    ]
    inits = [
        h.make_tensor("ax2", T.INT64, [1], [2]),
        h.make_tensor("shape2", T.INT64, [2], [0, -1]),
    ]
    inputs = [h.make_tensor_value_info("Q", dt, ["b", "d"])]
    if dt == T.FLOAT:
        # CPU template: KT is a normal input (numpy buffer is used without copying).
        inputs.append(h.make_tensor_value_info("KT", dt, ["d", "n"]))
    # GPU (fp16) template: KT is intentionally absent. The app inserts the real
    # [d, n] key matrix as a constant (dif/onnx_min.py), so ONNX Runtime uploads
    # it once to the session's own DirectML device. Binding a separately created
    # GPU buffer instead is unsafe on DirectML (device-removed errors).
    inputs += [
        h.make_tensor_value_info("k", T.INT64, [1]),
        h.make_tensor_value_info("shape3", T.INT64, [3]),   # [0, n // C, C]
        h.make_tensor_value_info("expand", T.INT64, [3]),   # [1, 1, C]
    ]
    outputs = [
        h.make_tensor_value_info("V", dt, ["b", "k"]),
        h.make_tensor_value_info("J", T.INT64, ["b", "k"]),
        h.make_tensor_value_info("CI", T.INT64, ["b", "k"]),
    ]
    g = h.make_graph(nodes, "knn_blocktopk", inputs, outputs, initializer=inits)
    m = h.make_model(g, opset_imports=[h.make_opsetid("", 18)])
    m.ir_version = 9
    if dt == T.FLOAT:
        onnx.checker.check_model(m)   # the fp16 template is completed at runtime
    return m


if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "models"), exist_ok=True)
    for name, dt in (("knn_fp16.onnx", T.FLOAT16), ("knn_fp32.onnx", T.FLOAT)):
        path = os.path.join(ROOT, "models", name)
        onnx.save(build(dt), path)
        print("saved", path)
