"""One-time developer tool: build models/ransac_support.onnx.

GPU part of the RANSAC pre-check of the crop-verification stage (DirectML; the
CUDA backend does the same in PyTorch, see dif/cuda.py). For each candidate image
pair the CPU proposes Hn homographies from random 4-match samples
(features.precheck_inputs); this graph counts, for every hypothesis, how many
matches it maps to within the reprojection threshold, and returns the best count.
A pair whose best count is far below worker.MIN_INLIERS cannot pass the geometric
check, so the CPU check is skipped for it.

Inputs for a batch of P pairs, matches padded to K (all float32, normalized coords):
    HM [P, Hn, 3, 3] hypotheses
    ST [P, 1, 3, K]  source points (x, y, 1), transposed
    DX [P, 1, K]     destination x
    DY [P, 1, K]     destination y
    MK [P, 1, K]     1 for real matches, 0 for padding
    TH [P, 1, 1]     squared threshold in normalized units
Output:
    CNT [P]          most matches supporting one hypothesis

Needs only `pip install onnx`.
"""

import os

import numpy as np
import onnx
import onnx.helper as h
from onnx import TensorProto as T
from onnx import numpy_helper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models", "ransac_support.onnx")


def build():
    c = lambda name, v: numpy_helper.from_array(np.array(v, np.int64), name)
    nodes = [
        h.make_node("MatMul", ["HM", "ST"], ["PR4"]),                    # [P, Hn, 3, K]
        h.make_node("Split", ["PR4", "split3"], ["X1", "Y1", "W1"], axis=2),
        h.make_node("Squeeze", ["X1", "ax2"], ["X"]),                     # [P, Hn, K]
        h.make_node("Squeeze", ["Y1", "ax2"], ["Y"]),
        h.make_node("Squeeze", ["W1", "ax2"], ["W"]),
        h.make_node("Div", ["X", "W"], ["XW"]),
        h.make_node("Div", ["Y", "W"], ["YW"]),
        h.make_node("Sub", ["XW", "DX"], ["EX"]),                         # DX [P,1,K] broadcasts
        h.make_node("Sub", ["YW", "DY"], ["EY"]),
        h.make_node("Mul", ["EX", "EX"], ["EX2"]),
        h.make_node("Mul", ["EY", "EY"], ["EY2"]),
        h.make_node("Add", ["EX2", "EY2"], ["E2"]),
        h.make_node("Less", ["E2", "TH"], ["IN"]),                        # NaN / inf -> False
        h.make_node("Cast", ["IN"], ["INF"], to=T.FLOAT),
        h.make_node("Mul", ["INF", "MK"], ["INM"]),
        h.make_node("ReduceSum", ["INM", "ax2"], ["CH"], keepdims=0),     # [P, Hn]
        h.make_node("ReduceMax", ["CH", "ax1"], ["CNT"], keepdims=0),     # [P]
    ]
    inits = [c("split3", [1, 1, 1]), c("ax1", [1]), c("ax2", [2])]
    f = lambda n, s: h.make_tensor_value_info(n, T.FLOAT, s)
    graph = h.make_graph(
        nodes, "ransac_support",
        [f("HM", ["P", "Hn", 3, 3]), f("ST", ["P", 1, 3, "K"]), f("DX", ["P", 1, "K"]),
         f("DY", ["P", 1, "K"]), f("MK", ["P", 1, "K"]), f("TH", ["P", 1, 1])],
        [f("CNT", ["P"])], inits)
    model = h.make_model(graph, opset_imports=[h.make_opsetid("", 18)], producer_name="dif")
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    onnx.save(build(), OUT)
    print("wrote", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
