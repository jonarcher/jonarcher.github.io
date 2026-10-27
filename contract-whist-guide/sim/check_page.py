"""Recompute the figures quoted on the page from results/. Run: python3 check_page.py

Needs results/ from the full runs (unit, values, guide --rule revised,
oracle --rule revised, examples). Prints each claim, what the page says, and
what the results give.
"""
import json
import math
import os
import re
from collections import defaultdict

import players

HERE = os.path.dirname(os.path.abspath(__file__))
R = os.path.join(HERE, "results")
rows_out = []


def claim(text, page, measured, tol):
    ok = abs(page - measured) <= tol
    rows_out.append((("ok  " if ok else "OFF "), text, page, measured))


def pct(x):
    return 100 * x


# ---- values.json: how often a card wins when every player tries to win every trick
values = json.load(open(os.path.join(R, "values.json")))


def rate(n, classes, seats=(0, 1, 2)):
    w = k = 0
    for key, by_seat in values.items():
        kn, cls = key.split("|")
        if int(kn) == n and any(cls.startswith(c) for c in classes):
            for s in seats:
                w += by_seat[str(s)][0]
                k += by_seat[str(s)][1]
    return pct(w / k)


ace_table = {7: (78, 75), 6: (71, 69), 5: (64, 62), 4: (56, 55), 3: (50, 47), 2: (48, 37)}
for n, (lead, follow) in ace_table.items():
    claim(f"side ace, {n} cards, leading", lead, rate(n, ["side A"], (0,)), 0.6)
    claim(f"side ace, {n} cards, 2nd/3rd", follow, rate(n, ["side A"], (1, 2)), 0.6)
claim("side ace, 7 cards, about 3 in 4", 75, rate(7, ["side A"]), 4)
claim("side king, 7 cards, about half", 50, rate(7, ["side K"]), 8)
claim("side queen, 7 cards, about 2 in 5", 40, rate(7, ["side Q"]), 5)
claim("side jack or lower, 7 cards, about 1 in 10", 10, rate(7, ["side J"]), 2)
claim("low trump (5-2), 7 cards, more often than not", 50, rate(7, ["trump 5-2"]), 100)
assert rate(7, ["trump 5-2"]) > 50

# ---- unit.txt: the one-card table
unit = open(os.path.join(R, "unit.txt")).read()
one_card = {"ace of trump": (100, 100), "king of trump": (96, 96), "2 of trump": (61, 60),
            "ace of side": (57, 18), "king of side": (54, 16), "queen of side": (52, 14), "2 of side": (26, 0)}
for label, (lead, follow) in one_card.items():
    m = re.search(rf"^{label}\s+([\d.]+)%\s+([\d.]+)%\s+([\d.]+)%", unit, re.M)
    claim(f"one card, {label}, leading", lead, float(m.group(1)), 0.6)
    claim(f"one card, {label}, 2nd/3rd", follow, (float(m.group(2)) + float(m.group(3))) / 2, 0.6)

# ---- guide-revised.txt: exact-bid rates by hand size and seat
guide = open(os.path.join(R, "guide-revised.txt")).read().splitlines()
hit = {}
n = None
for line in guide:
    m = re.match(r"^(\d)?\s+(lead|2nd|dealer|all)\s+([\d.]+)\s+([\d.]+)%", line)
    if m:
        n = int(m.group(1)) if m.group(1) else n
        hit[(n, m.group(2))] = float(m.group(4))
claim("hit rate, 1 card, 2nd bidder", 89, hit[(1, "2nd")], 0.6)
claim("hit rate, 1 card, dealer", 43, hit[(1, "dealer")], 0.6)
claim("hit rate, 7 cards, 2nd bidder", 46, hit[(7, "2nd")], 0.6)
claim("hit rate, 7 cards, dealer", 43, hit[(7, "dealer")], 0.6)
claim("hit rate, all seats, 7 cards (note: about half)", 46, hit[(7, "all")], 0.6)

# ---- oracle-revised.jsonl: best bids, rounding, the hook, the dealer
rows = [json.loads(l) for l in open(os.path.join(R, "oracle-revised.jsonl"))]
zero = defaultdict(lambda: [0, 0])
for r in rows:
    zero[r["n"]][0] += r["best"] == 0
    zero[r["n"]][1] += 1
for n, page in ((7, 10), (3, 40), (2, 60), (1, 60)):
    claim(f"best bid is 0, {n} cards, about {page}%", page, pct(zero[n][0] / zero[n][1]), 5)


def pooled(r, b):
    return (r["scoreA"][b] + r["scoreB"][b]) / 2


def estimate(r):
    return players.revised_guide(r["hand"], r["turned"] // 13, r["n"], r["seat"], r["earlier"])


# halves down against halves up, everything else the same
down = up = m = 0
for r in rows:
    est = estimate(r)
    bd = players.bid(est, r["n"], r["seat"], r["earlier"])
    bu = players.bid(est + 1e-6, r["n"], r["seat"], r["earlier"])
    down += pooled(r, bd)
    up += pooled(r, bu)
    m += 1
claim("halves down beat halves up (points a hand, small)", 0.0, (down - up) / m, 0.5)
assert down > up, "halves down should score higher"

# the hook: when the count is exactly the barred number, lower against higher
lo = hi = k = 0
for r in rows:
    if r["seat"] != 2:
        continue
    n, est = r["n"], estimate(r)
    b0 = max(0, min(n, math.ceil(est - 0.5)))
    if b0 != n - sum(r["earlier"]) or est != b0:
        continue
    if b0 - 1 < 0 or b0 + 1 > n:
        continue
    lo += pooled(r, b0 - 1)
    hi += pooled(r, b0 + 1)
    k += 1
claim("hook, count exactly the barred number: lower beats higher by about 1.5", 1.5, (lo - hi) / k, 0.5)

# the dealer leaning a little toward the tricks nobody has bid for (4+ cards)
base = lean = k = 0
for r in rows:
    if r["seat"] != 2 or r["n"] < 4:
        continue
    n, est = r["n"], estimate(r)
    slack = n - sum(r["earlier"])
    est2 = 0.8 * est + 0.2 * slack
    base += pooled(r, players.bid(est, n, 2, r["earlier"]))
    lean += pooled(r, players.bid(est2, n, 2, r["earlier"]))
    k += 1
claim("dealer leaning 1/5 toward unbid tricks, 4+ cards: gain in points a hand", 0.2, (lean - base) / k, 0.2)
assert lean > base

# ---- examples-revised.txt
ex = open(os.path.join(R, "examples-revised.txt")).read()
blocks = re.split(r"\n\n(?=\S)", ex)


def bid_hit(prefix, b):
    for blk in blocks:
        if blk.startswith(prefix):
            m = re.search(rf"bid {b}: exactly right\s+([\d.]+)%", blk)
            return float(m.group(1))
    raise KeyError(prefix)


for prefix, b, page in (("7 cards, hand 1", 4, 45), ("7 cards, hand 1", 5, 36), ("7 cards, hand 2", 0, 79),
                        ("7 cards, hand 2", 1, 37), ("7 cards, hand 3", 5, 45), ("7 cards, hand 3", 6, 27),
                        ("7 cards, hand 3", 4, 23), ("7 cards, hand 4", 2, 44), ("7 cards, hand 4", 3, 41),
                        ("3 cards, leading: 7D", 1, 47), ("3 cards, leading: 7D", 2, 40),
                        ("2 cards, leading: 5D", 1, 44), ("2 cards, leading: 5D", 2, 39), ("2 cards, leading: 5D", 0, 14)):
    claim(f"{prefix}: bid {b} exactly right", page, bid_hit(prefix, b), 0.7)

width = max(len(t) for _, t, _, _ in rows_out)
for flag, text, page, measured in rows_out:
    print(f"{flag} {text:<{width}}  page {page:>6}  results {measured:>7.2f}")
bad = [r for r in rows_out if r[0] == "OFF "]
print(f"\n{len(rows_out) - len(bad)} of {len(rows_out)} within tolerance" + (f"; {len(bad)} to look at" if bad else ""))
