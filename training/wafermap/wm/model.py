"""W3: compact residual CNN, focal loss with class-balanced weights, dihedral augmentation."""

from __future__ import annotations

import torch
from torch import nn
from torch.nn import functional as F

EMBEDDING_DIM = 128


class Block(nn.Module):
    def __init__(self, cin: int, cout: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(cout)
        self.conv2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(cout)
        self.skip = (
            nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))
            if stride != 1 or cin != cout
            else nn.Identity()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        return F.relu(out + self.skip(x))


class WaferNet(nn.Module):
    """Input [N, 3, 64, 64] one-hot (no_die, pass, fail). Returns logits and L2-normalised
    embedding [N, 128] (the penultimate layer)."""

    def __init__(self, num_classes: int, widths: tuple[int, ...] = (32, 64, 128, 256)) -> None:
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(3, widths[0], 3, 1, 1, bias=False), nn.BatchNorm2d(widths[0]), nn.ReLU()
        )
        layers: list[nn.Module] = []
        cin = widths[0]
        # Every stage halves the grid (64 -> 32 -> 16 -> 8 -> 4). Most source maps are about
        # 30x30 dies, so the 64x64 grid mostly repeats cells and full-resolution stages buy little.
        for w in widths:
            layers += [Block(cin, w, 2), Block(w, w)]
            cin = w
        self.features = nn.Sequential(*layers)
        self.project = nn.Sequential(
            nn.Linear(cin, EMBEDDING_DIM), nn.BatchNorm1d(EMBEDDING_DIM), nn.ReLU()
        )
        self.dropout = nn.Dropout(0.2)
        self.head = nn.Linear(EMBEDDING_DIM, num_classes)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.features(self.stem(x)).mean(dim=(2, 3))
        h = self.project(h)
        logits = self.head(self.dropout(h))
        return logits, F.normalize(h.float(), dim=1)


def class_balanced_weights(counts: torch.Tensor, beta: float = 0.9999) -> torch.Tensor:
    """Cui et al. (2019): weight proportional to 1 / effective number, normalised to mean 1."""
    effective = (1.0 - torch.pow(beta, counts.double())) / (1.0 - beta)
    weights = 1.0 / effective
    return (weights / weights.sum() * len(counts)).float()


def focal_loss(
    logits: torch.Tensor, target: torch.Tensor, weights: torch.Tensor, gamma: float = 2.0
) -> torch.Tensor:
    """Lin et al. (2017) focal loss with per-class weights, averaged over the batch."""
    log_p = F.log_softmax(logits.float(), dim=1).gather(1, target[:, None]).squeeze(1)
    loss = -weights[target] * (1.0 - log_p.exp()).pow(gamma) * log_p
    return loss.mean()


def dihedral(x: torch.Tensor, element: int) -> torch.Tensor:
    """One of the 8 symmetries of the square: rotate by element % 4 quarter turns, then
    transpose if element >= 4. x is [..., H, W]."""
    x = torch.rot90(x, element % 4, dims=(-2, -1))
    return x.transpose(-2, -1) if element >= 4 else x


def random_dihedral(x: torch.Tensor, generator: torch.Generator) -> torch.Tensor:
    """Apply an independent uniformly drawn dihedral element to each map in x [N, H, H]."""
    n, h, w = x.shape
    grid = torch.arange(h * w, device=x.device).view(h, w)
    table = torch.stack([dihedral(grid, e).reshape(-1) for e in range(8)])  # [8, H*W]
    elements = torch.randint(0, 8, (n,), generator=generator, device=x.device)
    return x.reshape(n, -1).gather(1, table[elements]).view(n, h, w)
