"""Read an IRIS-style linear model file (.model) and solve it.

The solver writes the model as
    G0 s_t = G1 s_{t-1} + c + Psi e_t + Pi eta_t
and applies Sims' gensys (QZ decomposition). The solution is
    s_t = T s_{t-1} + C + R_0 e_t + sum_{j>=1} R_j E_t e_{t+j}
where R_j (j >= 1) are the effects of anticipated future shocks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import scipy.linalg as sla
import sympy as sp
import yaml

SECTION_RE = re.compile(r"^\s*!(\w+)")
TIME_RE = re.compile(r"([A-Za-z_]\w*)\{([+-]?\d+)\}")
NAME_RE = re.compile(r"[A-Za-z_]\w*")


# --------------------------------------------------------------------------- parsing
def _strip_comments(text: str) -> str:
    return "\n".join(line.split("%", 1)[0] for line in text.splitlines())


def _split_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            current = m.group(1)
            sections.setdefault(current, [])
            continue
        if current:
            sections[current].append(line)
    return {k: "\n".join(v) for k, v in sections.items()}


def _parse_names(block: str) -> tuple[list[str], dict[str, str]]:
    """Variable declarations: optional 'label' followed by a name."""
    names, labels = [], {}
    for line in block.splitlines():
        line = line.split("%", 1)[0]
        label = None
        m = re.search(r"'([^']*)'|\"([^\"]*)\"", line)
        if m:
            label = m.group(1) or m.group(2)
            line = line[: m.start()] + line[m.end():]
        for name in NAME_RE.findall(line):
            names.append(name)
            if label:
                labels[name] = label
    return names, labels


def _parse_equations(block: str) -> list[str]:
    text = _strip_comments(block)
    return [e.strip() for e in text.split(";") if e.strip()]


def _encode_time(expr: str) -> str:
    def rep(m):
        name, k = m.group(1), int(m.group(2))
        if k == 0:
            return name
        return f"{name}__{'L' if k < 0 else 'F'}{abs(k)}"
    return TIME_RE.sub(rep, expr)


def _decode_symbol(sym: str) -> tuple[str, int]:
    m = re.fullmatch(r"(.+)__([LF])(\d+)", sym)
    if not m:
        return sym, 0
    return m.group(1), (-1 if m.group(2) == "L" else 1) * int(m.group(3))


def _linearize(eq: str, params: dict[str, float]):
    """Return ({(name, shift): coef}, const) for 'lhs = rhs' as lhs - rhs = 0."""
    if "=" in eq:
        lhs, rhs = eq.split("=", 1)
        expr_s = f"({lhs}) - ({rhs})"
    else:
        expr_s = eq
    expr_s = _encode_time(expr_s)
    idents = set(NAME_RE.findall(expr_s))
    local = {n: sp.Symbol(n) for n in idents}
    expr = sp.parse_expr(expr_s, local_dict=local, evaluate=True)
    subs = {local[n]: sp.Float(params[n]) for n in idents if n in params}
    expr = sp.expand(expr.subs(subs))
    syms = sorted(expr.free_symbols, key=lambda s: s.name)
    coefs = {}
    for s in syms:
        c = sp.diff(expr, s)
        if c.free_symbols:
            raise ValueError(f"Nonlinear term in equation: {eq}")
        coefs[_decode_symbol(s.name)] = float(c)
    const = float(expr.subs({s: 0 for s in syms}))
    return coefs, const


# --------------------------------------------------------------------------- gensys
def gensys(g0, g1, c, psi, pi, div=1.0 + 1e-8, realsmall=1e-6):
    """Port of Sims' gensys.m (the same algorithm IRIS uses for linear rational-expectations models).

    Steps: QZ-decompose (g0, g1) and order the generalized eigenvalues so the unstable ones (|root| > div) come
    last; the number of unstable roots must equal the number of expectation errors that can be solved out
    (Blanchard–Kahn: `exists` if enough, `unique` if not too many); then build the stable solution
    s_t = T s_{t-1} + C + impact e_t, plus (fmat, fwt, ywt) that give the effect of shocks anticipated j periods
    ahead: ywt fmat^(j-1) fwt (used by Model.R)."""
    n = g0.shape[0]

    def stable(alpha, beta):
        # root of g0 s_t = g1 s_{t-1} is beta/alpha in Sims' notation (b_ii/a_ii)
        return np.abs(beta) < div * np.abs(alpha)

    a, b, _, _, Q, Z = sla.ordqz(g0, g1, sort=stable, output="complex")
    q = Q.conj().T  # Sims: q*g0*z = a
    z = Z
    da, db = np.abs(np.diag(a)), np.abs(np.diag(b))
    if np.any((da < realsmall) & (db < realsmall)):
        raise RuntimeError("Coincident zeros: indeterminacy and/or nonexistence")
    nunstab = int(np.sum(db > div * da))
    ns = n - nunstab
    q1, q2 = q[:ns, :], q[ns:, :]
    neta = pi.shape[1]

    etawt = q2 @ pi
    if nunstab == 0:
        ueta = np.zeros((0, 0)); deta = np.zeros((0, 0)); veta = np.zeros((neta, 0))
        nbig = 0
    else:
        u, d, vh = np.linalg.svd(etawt, full_matrices=False)
        big = d > realsmall
        nbig = int(big.sum())
        ueta, deta, veta = u[:, big], np.diag(d[big]), vh.conj().T[:, big]
    exists = nbig >= nunstab

    etawt1 = q1 @ pi
    if ns == 0:
        ueta1 = np.zeros((0, 0)); deta1 = np.zeros((0, 0)); veta1 = np.zeros((neta, 0))
    else:
        u1, d1, vh1 = np.linalg.svd(etawt1, full_matrices=False)
        big1 = d1 > realsmall
        ueta1, deta1, veta1 = u1[:, big1], np.diag(d1[big1]), vh1.conj().T[:, big1]
    if veta1.size == 0:
        unique = True
    else:
        loose = veta1 - veta @ veta.conj().T @ veta1
        unique = int(np.sum(np.linalg.svd(loose, compute_uv=False) > realsmall * n)) == 0

    if nunstab and veta1.size:
        tmat_r = -(ueta @ np.linalg.solve(deta, veta.conj().T) @ veta1 @ deta1 @ ueta1.conj().T).conj().T
    else:
        tmat_r = np.zeros((ns, nunstab), dtype=complex)
    tmat = np.hstack([np.eye(ns), tmat_r])
    G0 = np.vstack([tmat @ a, np.hstack([np.zeros((nunstab, ns)), np.eye(nunstab)])])
    G1 = np.vstack([tmat @ b, np.zeros((nunstab, n))])
    G0I = np.linalg.inv(G0)
    G1 = G0I @ G1
    us = slice(ns, n)
    a22, b22 = a[us, us], b[us, us]
    C = G0I @ np.concatenate([tmat @ q @ c, np.linalg.solve(a22 - b22, q2 @ c) if nunstab else np.zeros(0)])
    impact = G0I @ np.vstack([tmat @ q @ psi, np.zeros((nunstab, psi.shape[1]))])
    fmat = np.linalg.solve(b22, a22) if nunstab else np.zeros((0, 0))
    fwt = -np.linalg.solve(b22, q2 @ psi) if nunstab else np.zeros((0, psi.shape[1]))
    ywt = G0I[:, us]
    return dict(
        T=np.real(z @ G1 @ z.conj().T),
        C=np.real(z @ C),
        impact=np.real(z @ impact),
        fmat=fmat, fwt=fwt, ywt=z @ ywt,
        eu=(exists, unique), nunstab=nunstab,
    )


# --------------------------------------------------------------------------- model
@dataclass
class Model:
    """Linear QPM read from an IRIS .model file, solved with gensys."""

    path: Path
    params: dict
    std: dict
    tvars: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    shocks: list[str] = field(default_factory=list)
    mvars: list[str] = field(default_factory=list)

    @classmethod
    def from_files(cls, model_file="model/model.model", params_file="model/params.yaml", **overrides):
        with open(params_file, encoding="utf-8") as f:
            p = yaml.safe_load(f)
        std = p.pop("std", {})
        p.update(overrides)
        m = cls(Path(model_file), p, std)
        m._read()
        m.solve()
        return m

    def with_params(self, **overrides) -> "Model":
        p = dict(self.params); p.update(overrides)
        m = Model(self.path, p, dict(self.std))
        m._read(); m.solve()
        return m

    # -- read
    def _read(self):
        text = self.path.read_text(encoding="utf-8")
        sec = _split_sections(text)
        self.tvars, self.labels = _parse_names(sec["transition_variables"])
        self.shocks, _ = _parse_names(sec["transition_shocks"])
        self.mvars, _ = _parse_names(sec.get("measurement_variables", ""))
        declared = set(_parse_names(sec.get("parameters", ""))[0])
        missing = declared - set(self.params)
        if missing:
            raise KeyError(f"Parameters missing in params.yaml: {sorted(missing)}")
        self.teqs_src = _parse_equations(sec["transition_equations"])
        self.meqs_src = _parse_equations(sec.get("measurement_equations", ""))
        if len(self.teqs_src) != len(self.tvars):
            raise ValueError(f"{len(self.teqs_src)} equations vs {len(self.tvars)} variables")
        self.teqs = [_linearize(e, self.params) for e in self.teqs_src]
        self.meqs = [_linearize(e, self.params) for e in self.meqs_src]

    # -- build canonical form and solve
    def solve(self):
        """Build the Sims form G0 s_t = G1 s_{t-1} + c + Psi e_t + Pi eta_t from the parsed linear equations and
        solve it with gensys.

        The state vector holds every transition variable at t, auxiliary lags (x_{t-1}, x_{t-2}, ... as extra states
        when an equation uses deeper lags) and auxiliary leads (E_t x_{t+1}, E_t x_{t+2}, ... when an equation uses
        leads); each lead adds an expectation error eta (the Pi column) whose elimination is what the Blanchard–Kahn
        counting of unstable roots achieves inside gensys."""
        tv = {v: i for i, v in enumerate(self.tvars)}
        sh = {s: i for i, s in enumerate(self.shocks)}
        maxlag = {v: 0 for v in self.tvars}
        maxlead = {v: 0 for v in self.tvars}
        for coefs, _ in self.teqs:
            for (name, k) in coefs:
                if name in tv:
                    if k < 0:
                        maxlag[name] = max(maxlag[name], -k)
                    elif k > 0:
                        maxlead[name] = max(maxlead[name], k)
        # state: tvars, lag aux (v_L1.. v_L{maxlag-1}), lead aux (v_F1..v_F{maxlead})
        states = list(self.tvars)
        for v in self.tvars:
            states += [f"{v}__L{j}" for j in range(1, maxlag[v])]
        for v in self.tvars:
            states += [f"{v}__F{j}" for j in range(1, maxlead[v] + 1)]
        si = {s: i for i, s in enumerate(states)}
        N, ns_, nexp = len(states), len(self.shocks), sum(maxlead.values())
        g0 = np.zeros((N, N)); g1 = np.zeros((N, N)); c = np.zeros(N)
        psi = np.zeros((N, ns_)); pi = np.zeros((N, nexp))

        def cur(name, k):
            """State index holding name_{t+k} dated at t (k >= 0) or t-1 (k < 0)."""
            if k == 0:
                return si[name], 0
            if k > 0:
                return si[f"{name}__F{k}"], 0
            if k == -1:
                return si[name], -1
            return si[f"{name}__L{-k - 1}"], -1

        # each parsed equation is "sum a_i * term_i + const = 0": terms dated t (or leads) go to G0, terms dated t-1
        # (or deeper lags) to G1 with the opposite sign, shocks to Psi, the constant to c
        row = 0
        for coefs, const in self.teqs:
            for (name, k), a in coefs.items():
                if name in sh:
                    if k != 0:
                        raise ValueError("Shocks with time subscripts are not supported")
                    psi[row, sh[name]] -= a
                elif name in tv:
                    idx, lag = cur(name, k)
                    if lag == 0:
                        g0[row, idx] += a
                    else:
                        g1[row, idx] -= a
                else:
                    raise KeyError(f"Unknown name {name}")
            c[row] = -const
            row += 1
        for v in self.tvars:  # lag identities
            for j in range(1, maxlag[v]):
                g0[row, si[f"{v}__L{j}"]] = 1
                g1[row, si[v] if j == 1 else si[f"{v}__L{j - 1}"]] = 1
                row += 1
        e = 0
        for v in self.tvars:  # expectation identities: x_t = F1_{t-1} + eta ; F_{j}_t = F_{j+1}_{t-1} + eta
            for j in range(1, maxlead[v] + 1):
                lhs = si[v] if j == 1 else si[f"{v}__F{j - 1}"]
                g0[row, lhs] = 1
                g1[row, si[f"{v}__F{j}"]] = 1
                pi[row, e] = 1
                e += 1; row += 1
        assert row == N
        sol = gensys(g0, g1, c, psi, pi)
        if not all(sol["eu"]):
            raise RuntimeError(f"Blanchard-Kahn conditions fail (existence, uniqueness) = {sol['eu']}")
        self.states, self.si, self.sol = states, si, sol
        # reduced form: s_t = T s_{t-1} + C + R0 e_t (+ effects of anticipated future shocks, see R(j))
        self.T, self.C, self.R0 = sol["T"], sol["C"], sol["impact"]
        self.n_states = N
        # measurement: Y = Z s + d — each !measurement_equations line "OBS = expr" is solved for OBS
        mv = {v: i for i, v in enumerate(self.mvars)}
        self.Zm = np.zeros((len(self.mvars), N)); self.dm = np.zeros(len(self.mvars))
        for coefs, const in self.meqs:
            ys = [n for (n, k) in coefs if n in mv]
            if len(ys) != 1:
                raise ValueError("Each measurement equation must contain exactly one measurement variable")
            i = mv[ys[0]]; ay = coefs[(ys[0], 0)]
            for (name, k), a in coefs.items():
                if name in tv:
                    if k != 0:
                        raise ValueError("Leads/lags in measurement equations are not supported")
                    self.Zm[i, si[name]] -= a / ay
            self.dm[i] = -const / ay
        return self

    def R(self, j: int) -> np.ndarray:
        """Impact of shock anticipated j periods ahead."""
        if j == 0:
            return self.R0
        s = self.sol
        if s["nunstab"] == 0:
            return np.zeros_like(self.R0)
        return np.real(s["ywt"] @ np.linalg.matrix_power(s["fmat"], j - 1) @ s["fwt"])

    def std_vector(self) -> np.ndarray:
        return np.array([float(self.std.get(s, 1.0)) for s in self.shocks])

    def check(self, nper=12, seed=0) -> float:
        """Max residual of the structural equations on a random simulated path (should be ~1e-10)."""
        rng = np.random.default_rng(seed)
        H = nper + 10
        eps = rng.normal(size=(H, len(self.shocks)))
        s = np.zeros((H + 1, self.n_states)); s[0] = rng.normal(size=self.n_states)
        # anticipated-shock simulation (perfect foresight) then check equations
        for t in range(1, H + 1):
            s[t] = self.T @ s[t - 1] + self.C + sum(self.R(j) @ eps[t - 1 + j] for j in range(0, H - t + 1))
        worst = 0.0
        for t in range(5, nper):
            for coefs, const in self.teqs:
                val = const
                for (name, k), a in coefs.items():
                    if name in self.shocks:
                        val += a * eps[t - 1, self.shocks.index(name)]
                    else:
                        val += a * s[t + k, self.si[name]]
                worst = max(worst, abs(val))
        return worst
