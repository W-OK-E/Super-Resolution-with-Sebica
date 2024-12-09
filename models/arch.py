import torch
import torch.nn as nn
import torch.nn.functional as F
from thop import profile
from thop import clever_format
import time

class CSA(nn.Module):
    def __init__(self, channel, kernel_size=3, reduction = 16,):
        super(CSA, self).__init__()
        self.spatial_attention = nn.Sequential(
            nn.Conv2d(2, 1, kernel_size=7, padding=3, bias=False),
            nn.Sigmoid()
        )
        # Bi-Directional
        self.channel_attention_forward = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv1d(1, 1, kernel_size=kernel_size, padding=(kernel_size-1)//2, bias=False),  # 1D卷积（正向）
            nn.Sigmoid()
        )
        self.channel_attention_backward = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv1d(1, 1, kernel_size=kernel_size, padding=(kernel_size-1)//2, bias=False),  # 1D卷积（反向）
            nn.Sigmoid()
        )

    def forward(self, x):  #(B,C,H,W)
        # Spatial attention
        avg_out = torch.mean(x, dim=1, keepdim=True) # (B,1,H，W）
        max_out, _ = torch.max(x, dim=1, keepdim=True) # (B,1,H，W）
        spatial_weight = torch.cat([avg_out, max_out], dim=1) # (B,2,H，W）
        spatial_weight = self.spatial_attention(spatial_weight) # (B,1,H，W）

        # Bi-Directional attention
        b, c, _, _ = x.size()
        y = torch.mean(x, dim=(2, 3), keepdim=True)  # （B，16,1,1）全局平均池化后的通道向量

        y_forward = self.channel_attention_forward(y.squeeze(-1).transpose(-1, -2)).transpose(-1, -2).unsqueeze(-1) ## （B，1,1,1）
        y_backward = self.channel_attention_backward(y.squeeze(-1).transpose(-1, -2).flip(dims=[1])).transpose(-1, -2).unsqueeze(-1) ##（B，1,1,1）

        channel_weight = (y_forward + y_backward.flip(dims=[1])) / 2
        channel_weight = channel_weight.expand_as(x) ## （B，16,H，W）

        out = x * spatial_weight * channel_weight
        return out

class Conv(nn.Module):
    def __init__(self, N):
        super(Conv, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(N, N * 2, 1),
            nn.BatchNorm2d(N * 2),
            nn.ReLU(inplace=True),
            nn.Conv2d(N * 2, N, 3, padding=1),
            nn.BatchNorm2d(N),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        return self.conv(x)


class FFN(nn.Module):
    def __init__(self, N):
        super().__init__()
        self.ffn = nn.Sequential(
            nn.Conv2d(N, N * 2, 1),
            nn.BatchNorm2d(N * 2),
            nn.GELU(),
            nn.Conv2d(N * 2, N, 1),
            nn.BatchNorm2d(N)
        )

    def forward(self, x):
        return self.ffn(x) + x


class Attn(nn.Module):
    def __init__(self, N):
        super().__init__()
        self.pre_mixer = Conv(N)
        self.post_mixer = FFN(N)
        self.attn = CSA(N, reduction=16)
        self.norm1 = nn.BatchNorm2d(N)
        self.norm2 = nn.BatchNorm2d(N)

    def forward(self, x):
        out = self.pre_mixer(x)
        out = self.norm1(out)
        out = self.attn(out)
        out = self.post_mixer(out)
        out = self.norm2(out)
        out += x
        return out


class RTSR(nn.Module):
    def __init__(self, sr_rate=4, N=16):  ### 16 or 8: mini
        super(RTSR, self).__init__()
        self.scale = sr_rate

        self.head = nn.Sequential(
            nn.Conv2d(3, N, 3, padding=1),
            nn.BatchNorm2d(N),
            nn.ReLU(inplace=True)
        )

        self.body = nn.Sequential(
            *[Attn(N) for _ in range(6)] ### for mini is 4
        )

        self.tail = nn.Sequential(
            nn.Conv2d(N, 3 * sr_rate * sr_rate, 1),
            nn.PixelShuffle(sr_rate)
        )

    def forward(self, x):
        head = self.head(x)

        body_out = head
        for attn_layer in self.body:
            body_out = attn_layer(body_out)

        h = self.tail(body_out)

        base = F.interpolate(x, scale_factor=self.scale, mode='bilinear', align_corners=False)

        out = h + base
        # out = base

        return out

if __name__ == '__main__':
    model = RTSR(sr_rate=4, N=16) ### 16, 8

    params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'Number of trainable parameters: {params}')

    input = torch.randn(1, 3, 224, 224)
    macs, params = profile(model, inputs=(input,))
    macs, params = clever_format([macs, params], "%.3f")
    print(f'GFLOPs: {macs}')

    input_tensor = torch.randn(1, 3, 224, 224).cuda()
    model = model.cuda()
    start_time = time.time()
    output = model(input_tensor)
    end_time = time.time()
    runtime_ms = (end_time - start_time) * 1000
    print(f'Runtime (ms): {runtime_ms}')