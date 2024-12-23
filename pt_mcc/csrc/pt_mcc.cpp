#include <torch/extension.h>

namespace pt_mcc
{

    void register_aabb(torch::Library &m);
    void register_compute_pdf(torch::Library &m);
    void register_find_neighbors(torch::Library &m);
    void register_poisson_sampling(torch::Library &m);
    void register_sort(torch::Library &m);
    void register_spatial_connv(torch::Library &m);
    void register_muladd(torch::Library &m);
}

// Registers _C as a Python extension module.
PYBIND11_MODULE(TORCH_EXTENSION_NAME, m)
{
}

// Defines the operatorss
TORCH_LIBRARY(pt_mcc, m)
{
    pt_mcc::register_aabb(m);
    pt_mcc::register_compute_pdf(m);
    pt_mcc::register_find_neighbors(m);
    pt_mcc::register_poisson_sampling(m);
    pt_mcc::register_sort(m);
    pt_mcc::register_spatial_connv(m);
    pt_mcc::register_muladd(m);
}
