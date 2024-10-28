import torch
from torch import Tensor

__all__ = ["mymuladd", "myadd_out"]


def mymuladd(a: Tensor, b: Tensor, c: float) -> Tensor:
    """Performs a * b + c in an efficient fused kernel"""
    return torch.ops.pt_mcc.mymuladd.default(a, b, c)

def compute_aabb(pts: Tensor, batch_ids: Tensor, batch_size: int, inv_inf: bool):
    return torch.ops.pt_mcc.compute_aabb.default(pts, batch_ids, batch_size, inv_inf)

def test():
    return torch.ops.pt_mcc.test()

@torch.library.register_fake("pt_mcc::test")
def _():
    return -1

@torch.library.register_fake("pt_mcc::compute_aabb")
def _(pts, batch_ids, batch_size, scale_inv):
    torch._check(pts.device == batch_ids.device)
    return (torch.empty_like(pts), torch.empty_like(pts))

# Registers a FakeTensor kernel (aka "meta kernel", "abstract impl")
# that describes what the properties of the output Tensor are given
# the properties of the input Tensor. The FakeTensor kernel is necessary
# for the op to work performantly with torch.compile.
@torch.library.register_fake("pt_mcc::mymuladd")
def _(a, b, c):
    torch._check(a.shape == b.shape)
    torch._check(a.dtype == torch.float)
    torch._check(b.dtype == torch.float)
    torch._check(a.device == b.device)
    return torch.empty_like(a)


def _backward(ctx, grad):
    a, b = ctx.saved_tensors
    grad_a, grad_b = None, None
    if ctx.needs_input_grad[0]:
        grad_a = torch.ops.pt_mcc.mymul.default(grad, b)
    if ctx.needs_input_grad[1]:
        grad_b = torch.ops.pt_mcc.mymul.default(grad, a)
    return grad_a, grad_b, None


def _setup_context(ctx, inputs, output):
    a, b, c = inputs
    saved_a, saved_b = None, None
    if ctx.needs_input_grad[0]:
        saved_b = b
    if ctx.needs_input_grad[1]:
        saved_a = a
    ctx.save_for_backward(saved_a, saved_b)


# This adds training support for the operator. You must provide us
# the backward formula for the operator and a `setup_context` function
# to save values to be used in the backward.
torch.library.register_autograd(
    "pt_mcc::mymuladd", _backward, setup_context=_setup_context)


@torch.library.register_fake("pt_mcc::mymul")
def _(a, b):
    torch._check(a.shape == b.shape)
    torch._check(a.dtype == torch.float)
    torch._check(b.dtype == torch.float)
    torch._check(a.device == b.device)
    return torch.empty_like(a)


def myadd_out(a: Tensor, b: Tensor, out: Tensor) -> None:
    """Writes a + b into out"""
    torch.ops.pt_mcc.myadd_out.default(a, b, out)