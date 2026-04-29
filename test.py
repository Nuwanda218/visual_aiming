import sys
print("python =", sys.executable)

import torch
print("torch =", torch.__version__)
print("torch.version.cuda =", torch.version.cuda)
print("cuda_available =", torch.cuda.is_available())
print("cuda_device_count =", torch.cuda.device_count())

if torch.cuda.is_available():
    print("cuda_device_0 =", torch.cuda.get_device_name(0))

import ultralytics
print("ultralytics =", ultralytics.__version__)
