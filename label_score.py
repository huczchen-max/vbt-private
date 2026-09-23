"""H24 — score the blind labels against the answer key (v0.1, 2026-09-23).

Pre-registered analysis (fixed before any label exists):
  primary   median 26-wk excess vs SPY, BUY set minus PASS set (listed and
            delisted together; the labeller could not tell them apart), with a
            permutation test (10,000 shuffles of the labels over the same rows)
            -> p-value for the observed difference; also ret26, win26, mae26,
            p10/p90, mean (the right tail), next-break shares
  bar       BUY-minus-PASS median excess >= +5 pts, BUY median excess > 0,
            p < 0.05, n_buy >= 60, and the sign holds within each of the
            decision-bar kinds that have >= 20 BUYs (CTRL is the honest one)
  secondary by kind, by year, by band position, by delisted, high-conviction
            BUYs vs the rest; the 'portfolio' view (equal-weight mean of BUYs
            vs the mean of everything shown = what a labeller who bought
            every chart would have earned)
  reliability  agreement on the repeated charts (dup_of): raw agreement and
            Cohen's kappa over yes/no/unsure; a labeller who disagrees with
            himself on > 25% of repeats cannot carry a signal of this size
Usage: python label_score.py --labels h24_labels_h24-24.csv --key private/label/label_key.csv --out private/label
"""
import argparse, json
import numpy as np, pandas as pd

def block(h, exc="exc26_SPY"):
    if not len(h): return dict(n=0)
    med = lambda x: (None if x.isna().all() else round(float(x.median()), 1))
    o = dict(n=int(len(h)), ret26_med=med(h.ret26), exc26_med=med(h[exc]), win26=round(float((h.ret26 > 0).mean()), 2), mae26_med=med(h.mae26),
             ret26_mean=round(float(h.ret26.mean()), 1), exc26_mean=round(float(h[exc].mean()), 1),
             p10_ret26=round(float(h.ret26.quantile(.1)), 1), p90_ret26=round(float(h.ret26.quantile(.9)), 1),
             next_up=round(float((h.next_break == "UP").mean()), 2), next_down=round(float((h.next_break == "DOWN").mean()), 2))
    if "ret52" in h and h.ret52.notna().sum() >= 10:
        o["ret52_med"] = med(h.ret52); o["exc52_med"] = med(h.exc52_SPY) if "exc52_SPY" in h else None
    return o

def perm_test(d, col="exc26_SPY", n=10000, seed=24):
    """Difference of medians BUY - PASS under label shuffling (unsure excluded)."""
    x = d[d.label.isin(["yes", "no"])].dropna(subset=[col]); v = x[col].values; lab = (x.label == "yes").values
    if lab.sum() < 5 or (~lab).sum() < 5: return dict(n_yes=int(lab.sum()), n_no=int((~lab).sum()), diff=None, p=None)
    obs = np.median(v[lab]) - np.median(v[~lab]); rng = np.random.default_rng(seed); cnt = 0
    for _ in range(n):
        p = rng.permutation(lab); cnt += (np.median(v[p]) - np.median(v[~p])) >= obs
    return dict(n_yes=int(lab.sum()), n_no=int((~lab).sum()), diff=round(float(obs), 1), p_one_sided=round(cnt / n, 4),
                mean_diff=round(float(v[lab].mean() - v[~lab].mean()), 1))

def kappa(a, b):
    cats = sorted(set(a) | set(b)); n = len(a)
    if n == 0: return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return round((po - pe) / (1 - pe), 2) if pe < 1 else None

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--labels", required=True); ap.add_argument("--key", required=True); ap.add_argument("--out", default=".")
    a = ap.parse_args()
    lab = pd.read_csv(a.labels, dtype={"id": str}); key = pd.read_csv(a.key, dtype={"id": str, "dup_of": str})
    key["dup_of"] = key.dup_of.fillna("")
    d = key.merge(lab[["id", "label", "star", "note"]], on="id", how="left")
    d["star"] = d.star.fillna(0).astype(int) == 1
    # reliability on repeats (before dropping them)
    reps = d[d.dup_of != ""].merge(d[d.dup_of == ""][["id", "label"]].rename(columns={"id": "dup_of", "label": "label_orig"}), on="dup_of")
    reps = reps.dropna(subset=["label", "label_orig"])
    rel = dict(n_pairs=int(len(reps)), agreement=(round(float((reps.label == reps.label_orig).mean()), 2) if len(reps) else None),
               kappa=(kappa(list(reps.label), list(reps.label_orig)) if len(reps) else None),
               buy_agreement=(round(float((reps[reps.label_orig == "yes"].label == "yes").mean()), 2) if (reps.label_orig == "yes").sum() else None))
    u = d[d.dup_of == ""].copy(); labelled = u.dropna(subset=["label"])
    cov = dict(charts=int(len(u)), labelled=int(len(labelled)), buy=int((labelled.label == "yes").sum()), pass_=int((labelled.label == "no").sum()), unsure=int((labelled.label == "unsure").sum()), star=int(labelled.star.sum()))
    out = dict(coverage=cov, reliability=rel,
               all_shown=block(u), buy=block(labelled[labelled.label == "yes"]), pass_=block(labelled[labelled.label == "no"]), unsure=block(labelled[labelled.label == "unsure"]),
               buy_star=block(labelled[(labelled.label == "yes") & labelled.star]), buy_nostar=block(labelled[(labelled.label == "yes") & ~labelled.star]),
               primary=perm_test(labelled), primary_ret26=perm_test(labelled, "ret26"),
               by_kind={k: dict(buy=block(h[h.label == "yes"]), pass_=block(h[h.label == "no"]), test=perm_test(h, n=3000)) for k, h in labelled.groupby("kind")},
               by_year={str(y): dict(n=int(len(h)), buy_exc=(None if not (h.label == "yes").any() else round(float(h[h.label == "yes"].exc26_SPY.median()), 1)), pass_exc=(None if not (h.label == "no").any() else round(float(h[h.label == "no"].exc26_SPY.median()), 1)), buy_share=round(float((h.label == "yes").mean()), 2)) for y, h in labelled.groupby("year")},
               by_delisted={str(k): dict(buy=block(h[h.label == "yes"]), pass_=block(h[h.label == "no"])) for k, h in labelled.groupby("delisted")},
               by_pos={str(k): dict(buy=block(h[h.label == "yes"]), pass_=block(h[h.label == "no"])) for k, h in labelled.groupby(pd.cut(labelled.pos, [-.01, .33, .66, 1.01], labels=["low", "mid", "top"]), observed=True)},
               buy_rate_by_kind={k: round(float((h.label == "yes").mean()), 2) for k, h in labelled.groupby("kind")},
               what_the_eye_likes={c: dict(buy=round(float(labelled[labelled.label == "yes"][c].median()), 3), pass_=round(float(labelled[labelled.label == "no"][c].median()), 3)) for c in ["pos", "rsi", "wk_since_low", "mad_med", "contr8", "vol_dry8", "rsi_slope26", "base_len"] if c in labelled and labelled[c].notna().any()})
    p = out["primary"]; b = out["buy"]; kinds_ok = [k for k, v in out["by_kind"].items() if v["buy"]["n"] >= 20]
    signs = {k: bool((out["by_kind"][k]["test"]["diff"] or 0) > 0) for k in kinds_ok}
    out["verdict"] = dict(bar_diff_ge_5=bool(p["diff"] is not None and p["diff"] >= 5), bar_buy_exc_positive=bool((b.get("exc26_med") or 0) > 0), bar_p_lt_05=bool(p.get("p_one_sided") is not None and p["p_one_sided"] < 0.05),
                          bar_n_buy_ge_60=bool(cov["buy"] >= 60), bar_sign_holds_by_kind=signs, bar_reliability_ge_75=bool((rel["agreement"] or 0) >= 0.75))
    out["verdict"]["clears_bar"] = bool(all([out["verdict"]["bar_diff_ge_5"], out["verdict"]["bar_buy_exc_positive"], out["verdict"]["bar_p_lt_05"], out["verdict"]["bar_n_buy_ge_60"], all(signs.values()) if signs else False, out["verdict"]["bar_reliability_ge_75"]]))
    json.dump(out, open(f"{a.out}/label_score.json", "w"), indent=1, default=str)
    md = [f"# H24 blind-labelling score\n", f"charts {cov['charts']} · labelled {cov['labelled']} · BUY {cov['buy']} (★ {cov['star']}) · PASS {cov['pass_']} · unsure {cov['unsure']} · repeat agreement {rel['agreement']} (κ {rel['kappa']}, n={rel['n_pairs']})\n",
          "| set | n | ret26 med | exc26 med | win | MAE | mean ret | p10 | p90 | next UP | next DOWN |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in ["all_shown", "buy", "buy_star", "pass_", "unsure"]:
        x = out[name]; md.append(f"| {name} | {x.get('n')} | {x.get('ret26_med')} | {x.get('exc26_med')} | {x.get('win26')} | {x.get('mae26_med')} | {x.get('ret26_mean')} | {x.get('p10_ret26')} | {x.get('p90_ret26')} | {x.get('next_up')} | {x.get('next_down')} |")
    md.append(f"\nprimary: BUY − PASS median exc26 = {p.get('diff')} pts, one-sided permutation p = {p.get('p_one_sided')} (n {p.get('n_yes')} vs {p.get('n_no')}); mean diff {p.get('mean_diff')}\n")
    md.append("| kind | BUYs | BUY exc26 | PASS exc26 | diff | p |"); md.append("|---|---|---|---|---|---|")
    for k, v in out["by_kind"].items(): md.append(f"| {k} | {v['buy']['n']} | {v['buy'].get('exc26_med')} | {v['pass_'].get('exc26_med')} | {v['test'].get('diff')} | {v['test'].get('p_one_sided')} |")
    md.append(f"\nverdict: {json.dumps(out['verdict'], default=str)}\n")
    open(f"{a.out}/label_score.md", "w").write("\n".join(md)); print("\n".join(md))

if __name__ == "__main__":
    main()
