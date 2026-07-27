"""Language-removal transforms, shared by the analysis and the parallel eval."""

from __future__ import annotations

import numpy as np

KAPPA = 10.0


def l2(X: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(X, axis=1, keepdims=True)
    return X / np.maximum(n, 1e-12)


def centered(X: np.ndarray, group: np.ndarray, kappa: float = KAPPA) -> np.ndarray:
    """Leave-one-out, shrunk per-group centering.

        mu_g^(-i) = (n_g * mean_g - x_i) / (n_g - 1)

    then shrunk toward the global mean by `kappa` pseudo-counts.

    Both corrections matter on this data. Without leave-one-out, a group of size
    one has its single point subtracted from itself and lands exactly on the
    origin — 28 of the 104 languages here have exactly one museum, so plain
    centering would manufacture a dense fake cluster. Shrinkage then keeps
    small-but-not-singleton groups from being centered by a noisy mean estimated
    from three or four points.

    Centroids are deliberately estimated within the corpus being transformed.
    Borrowing them from the all-articles pool would give tighter estimates but
    would import that pool's skew toward museums covered in many languages.
    """
    out = np.empty_like(X)
    g = X.mean(axis=0)
    for key in np.unique(group):
        idx = np.flatnonzero(group == key)
        sub = X[idx]
        n = len(idx)
        if n > 1:
            loo = (sub.sum(axis=0) - sub) / (n - 1)
            n_loo = n - 1
        else:
            loo = np.zeros_like(sub)
            n_loo = 0
        mu = (n_loo * loo + kappa * g) / (n_loo + kappa)
        out[idx] = sub - mu
    return l2(out)


def inlp(X: np.ndarray, y: np.ndarray, iters: int = 3, verbose: bool = True):
    """Iterative nullspace projection against a linear classifier for `y`.

    Note the plateau: on this data linear language accuracy collapses after a
    single projection and further iterations only strip dimensions. Stop early.
    """
    from sklearn.linear_model import LogisticRegression

    W = X.copy()
    d = X.shape[1]
    removed = 0
    accs = []
    for i in range(iters):
        clf = LogisticRegression(max_iter=400, C=1.0, n_jobs=-1)
        clf.fit(W, y)
        accs.append(float(clf.score(W, y)))
        Q, R = np.linalg.qr(clf.coef_.T)
        rank = int((np.abs(np.diag(R)) > 1e-8).sum())
        Q = Q[:, :rank]
        W = W - (W @ Q) @ Q.T
        removed += rank
        if verbose:
            print(f"    inlp iter {i + 1}: train acc before projection {accs[-1]:.3f}, "
                  f"removed {rank} dims (total {removed}/{d})")
    return l2(W), removed, accs
