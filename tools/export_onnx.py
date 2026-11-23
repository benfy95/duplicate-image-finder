"""One-time developer tool: export the DINOv2-small feature model to ONNX.

The app itself does NOT need PyTorch; it runs models/dinov2_vits14_224.onnx with
ONNX Runtime (DirectML GPU or CPU). Re-run this only to regenerate the model:

    pip install -r requirements-dev.txt
    python tools/export_onnx.py

The exported graph takes raw pixels and does all preprocessing itself:
    input  "pixels":   uint8  [batch, 224, 224, 3]  (RGB)
    output "features": float32 [batch, 384]          (L2-normalized)
"""

import os
import sys

import numpy as np
import torch
import torch.nn.functional as F
import timm

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "models", "dinov2_vits14_224.onnx")
MODEL_NAME = "vit_small_patch14_dinov2.lvd142m"


OUT16 = os.path.join(ROOT, "models", "dinov2_vits14_224_fp16.onnx")


class Wrapped(torch.nn.Module):
    def __init__(self, fp16=False):
        super().__init__()
        self.fp16 = fp16
        self.net = timm.create_model(MODEL_NAME, pretrained=True, num_classes=0, img_size=224).eval()
        if fp16:
            self.net.half()
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def forward(self, pixels):
        x = pixels.permute(0, 3, 1, 2).float() / 255.0
        x = (x - self.mean) / self.std
        if self.fp16:                      # fp16 network body (GPU), fp32 in/out
            x = x.half()
        return F.normalize(self.net(x).float(), dim=1)


def export(fp16, path):
    m = Wrapped(fp16)
    dummy = torch.randint(0, 255, (2, 224, 224, 3), dtype=torch.uint8)
    torch.onnx.export(
        m, (dummy,), path, input_names=["pixels"], output_names=["features"],
        dynamic_axes={"pixels": {0: "batch"}, "features": {0: "batch"}},
        opset_version=18, dynamo=False, external_data=False,
    )
    return m


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    ref_model = export(False, OUT)
    export(True, OUT16)        # used on the GPU (about 2x faster on DirectML)
    # verify both against PyTorch fp32
    import onnxruntime as ort
    test = torch.randint(0, 255, (4, 224, 224, 3), dtype=torch.uint8)
    with torch.no_grad():
        ref = ref_model(test).numpy()
    for path, prov, tol in ((OUT, "CPUExecutionProvider", 0.9999), (OUT16, "DmlExecutionProvider", 0.999)):
        so = ort.SessionOptions()
        so.enable_mem_pattern = False
        sess = ort.InferenceSession(path, so, providers=[prov, "CPUExecutionProvider"])
        out = sess.run(None, {"pixels": test.numpy()})[0]
        cos = (ref * out).sum(1)
        print(f"saved {path} ({os.path.getsize(path) / 2**20:.1f} MB); cosine vs PyTorch: {cos.min():.6f}")
        if cos.min() < tol:
            sys.exit("export mismatch")


if __name__ == "__main__":
    main()
