"""Experiments behind the bidding guide. Run: python3 experiments.py <name> [--quick]

  unit    one-card win rates by seat, against closed-form figures
  values  how often each class of card wins a trick, by hand size and seat
  guide   how a bidding rule scores when all three players follow it
  oracle  the best bid for a hand, found by trying every bid, against the rule
  examples  every bid for the example hands on the page, tried against random opponents

--rule NAME picks the bidding rule from players.RULES (default: revised).
Everything is seeded, so a run reproduces the same figures.
"""
import json
import os
import random
import sys
from collections import defaultdict
from multiprocessing import Pool

import players
from whist import ACE, JACK, KING, QUEEN, deal, play_hand, score

SIZES = range(1, 8)
WORKERS = os.cpu_count() or 4
RESULTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


def parallel(fn, tasks):
    with Pool(WORKERS) as pool:
        return pool.map(fn, tasks, chunksize=1)


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


# ---------------------------------------------------------------- unit check

def _unit_task(args):
    seed, count = args
    rng = random.Random(seed)
    tally = defaultdict(lambda: [0, 0])
    for _ in range(count):
        hands, turned = deal(rng, 1)
        trump = turned // 13
        record = []
        play_hand(hands, trump, turned, (0, 0, 0), greedy=(True, True, True), record=record)
        winner = record[0][0]
        for seat in range(3):
            c = hands[seat][0]
            s, r = divmod(c, 13)
            kind = "trump" if s == trump else "side"
            label = {12: "ace", 11: "king", 10: "queen", 0: "2"}.get(r)
            if label:
                t = tally[(f"{label} of {kind}", seat)]
                t[0] += winner == seat
                t[1] += 1
    return dict(tally)


def unit(quick):
    total = 200_000 if quick else 2_000_000
    chunks = WORKERS * 4
    results = parallel(_unit_task, [(i, total // chunks) for i in range(chunks)])
    merged = defaultdict(lambda: [0, 0])
    for r in results:
        for k, (w, n) in r.items():
            merged[k][0] += w
            merged[k][1] += n
    print(f"One-card deals ({total:,} deals). Chance a card wins its trick.\n")
    print(f"{'card':<16}{'lead':>8}{'2nd':>8}{'3rd':>8}")
    for label in ("ace of trump", "king of trump", "2 of trump", "ace of side", "king of side", "queen of side", "2 of side"):
        row = [merged[(label, seat)] for seat in range(3)]
        print(f"{label:<16}" + "".join(f"{100 * w / n:>7.1f}%" for w, n in row))
    # Closed forms. A player sees their own card and the turned trump, which
    # leaves 50 unseen cards for the opponents' two.
    print("\nClosed form:")
    print(f"  king of trump   {1 - (11 / 12) * (2 / 50):.3f}  loses only to the ace of trump, and only if it wasn't the card turned up")
    print(f"  2 of trump      {(39 / 50) * (38 / 49):.3f}  wins if neither opponent holds one of the other 11 trumps")
    print(f"  ace of side     {(38 / 50) * (37 / 49):.3f}  leading: wins if neither opponent holds one of the 12 trumps")


# ------------------------------------------------------------- card values

def card_class(card, hand, trump):
    s, r = divmod(card, 13)
    if s == trump:
        held = sum(1 for c in hand if c // 13 == trump)
        grp = {ACE: "A", KING: "K", QUEEN: "Q", JACK: "J"}.get(r) or ("10-6" if r >= 4 else "5-2")
        return ("trump " + grp) + ("" if grp in "AK" else " (1-2 trumps)" if held <= 2 else " (3+ trumps)")
    length = sum(1 for c in hand if c // 13 == s)
    grp = {ACE: "A", KING: "K", QUEEN: "Q"}.get(r)
    if grp is None:
        return "side J or lower"
    if grp == "A":
        return "side A"
    return f"side {grp} ({'1' if length == 1 else '2' if length == 2 else '3+'} cards in suit)"


def _values_task(args):
    n, seed, count = args
    rng = random.Random(seed)
    tally = defaultdict(lambda: [0, 0])
    for _ in range(count):
        hands, turned = deal(rng, n)
        trump = turned // 13
        record = []
        play_hand(hands, trump, turned, (0, 0, 0), greedy=(True, True, True), record=record)
        won = {card for _, card in record}
        for seat in range(3):
            for c in hands[seat]:
                t = tally[(card_class(c, hands[seat], trump), seat)]
                t[0] += c in won
                t[1] += 1
    return n, dict(tally)


def values(quick):
    total = 20_000 if quick else 400_000
    chunks = WORKERS * 2
    tasks = [(n, f"values-{n}-{i}", total // chunks) for n in SIZES for i in range(chunks)]
    merged = defaultdict(lambda: [0, 0])
    for n, r in parallel(_values_task, tasks):
        for (cls, seat), (w, k) in r.items():
            merged[(n, cls, seat)][0] += w
            merged[(n, cls, seat)][1] += k
    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "values.json"), "w") as f:
        rates = defaultdict(dict)
        for (n, cls, seat), (w, k) in sorted(merged.items()):
            rates[f"{n}|{cls}"][seat] = [w, k]
        json.dump(rates, f, indent=0)
    print(f"Chance a card wins a trick when every player tries to win every trick ({total:,} deals per hand size).\n")
    classes = sorted({k[1] for k in merged}, key=lambda c: (c.split()[0] != "trump", c))
    for n in SIZES:
        print(f"{n}-card hands          lead     2nd     3rd")
        for cls in classes:
            cells = [merged.get((n, cls, seat)) for seat in range(3)]
            if not all(cells) or min(k for _, k in cells) < 200:
                continue
            print(f"  {cls:<30}" + "".join(f"{100 * w / k:>7.1f}%" for w, k in cells))
        print()


# ------------------------------------------------------------ guide scoring

def _guide_task(args):
    n, seed, count, rule_name = args
    rule = players.RULES[rule_name]
    rng = random.Random(seed)
    # per seat: score, hits, bid, tricks
    acc = [[0, 0, 0, 0] for _ in range(3)]
    for _ in range(count):
        hands, turned = deal(rng, n)
        trump = turned // 13
        bids = players.make_bids(hands, trump, n, [rule] * 3)
        won = play_hand(hands, trump, turned, bids)
        for s in range(3):
            a = acc[s]
            a[0] += score(bids[s], won[s])
            a[1] += bids[s] == won[s]
            a[2] += bids[s]
            a[3] += won[s]
    return n, acc


def guide(quick):
    rule_name = arg("--rule", "revised")
    total = 20_000 if quick else 300_000
    chunks = WORKERS * 2
    tasks = [(n, f"guide-{rule_name}-{n}-{i}", total // chunks, rule_name) for n in SIZES for i in range(chunks)]
    merged = {n: [[0, 0, 0, 0] for _ in range(3)] for n in SIZES}
    for n, acc in parallel(_guide_task, tasks):
        for s in range(3):
            for j in range(4):
                merged[n][s][j] += acc[s][j]
    games = (total // chunks) * chunks
    print(f"Rule '{rule_name}', all three players using it ({games:,} deals per hand size).")
    print("score = tricks + 10 for an exact bid. bias = average bid minus average tricks won.\n")
    print(f"{'cards':<7}{'seat':<8}{'score':>7}{'hit %':>8}{'bid':>7}{'tricks':>8}{'bias':>7}")
    for n in SIZES:
        for s, label in enumerate(("lead", "2nd", "dealer")):
            sc, hit, bid, tr = merged[n][s]
            print(f"{n if s == 0 else '':<7}{label:<8}{sc / games:>7.2f}{100 * hit / games:>7.1f}%{bid / games:>7.2f}{tr / games:>8.2f}{(bid - tr) / games:>+7.2f}")
        tot = [sum(merged[n][s][j] for s in range(3)) for j in range(4)]
        print(f"{'':<7}{'all':<8}{tot[0] / games / 3:>7.2f}{100 * tot[1] / games / 3:>7.1f}%{tot[2] / games / 3:>7.2f}{tot[3] / games / 3:>8.2f}{(tot[2] - tot[3]) / games / 3:>+7.2f}")


# ------------------------------------------------------------------- oracle

def _sample_opponents(rng, mine, turned, n, seat, rules, observed):
    """Deal the other two hands at random, keeping only deals in which the
    players who bid before `seat` would have bid what they did."""
    rest = [c for c in range(52) if c not in mine and c != turned]
    trump = turned // 13
    for _ in range(600):
        rng.shuffle(rest)
        hands = [None, None, None]
        hands[seat] = mine
        others = [s for s in range(3) if s != seat]
        hands[others[0]] = sorted(rest[:n])
        hands[others[1]] = sorted(rest[n:2 * n])
        ok = True
        bids = []
        for j in range(seat):
            est = rules[j](hands[j], trump, n, j, bids)
            b = players.bid(est, n, j, bids)
            if b != observed[j]:
                ok = False
                break
            bids.append(b)
        if ok:
            return hands
    return None


def _focal_outcomes(hands, turned, n, seat, earlier, rules, legal, rule_for_later):
    """Tricks the focal player wins for each legal bid in this one deal."""
    trump = turned // 13
    out = {}
    for b in legal:
        bids = list(earlier) + [b]
        for j in range(seat + 1, 3):
            est = rule_for_later(hands[j], trump, n, j, bids)
            bids.append(players.bid(est, n, j, bids))
        won = play_hand(hands, trump, turned, bids)
        out[b] = won[seat]
    return out


def _oracle_task(args):
    n, seat, chunk, count, k, rule_name = args
    rule = players.RULES[rule_name]
    rules = [rule] * 3
    rng = random.Random(f"oracle-{rule_name}-{n}-{seat}-{chunk}")
    rows = []
    for _ in range(count):
        hands, turned = deal(rng, n)
        trump = turned // 13
        observed = players.make_bids(hands, trump, n, rules)
        mine = hands[seat]
        earlier = observed[:seat]
        legal = [b for b in range(n + 1) if not (seat == 2 and sum(earlier) + b == n)]
        sums = {"A": defaultdict(float), "B": defaultdict(float)}
        hits = defaultdict(float)
        got = {"A": 0, "B": 0}
        for half in ("A", "B"):
            for _ in range(k):
                sample = _sample_opponents(rng, mine, turned, n, seat, rules, observed)
                if sample is None:
                    break
                tricks = _focal_outcomes(sample, turned, n, seat, earlier, rules, legal, rule)
                for b, t in tricks.items():
                    sums[half][b] += score(b, t)
                    if half == "B":
                        hits[b] += b == t
                got[half] += 1
        if min(got.values()) < k // 2:
            continue
        mean = {h: {b: sums[h][b] / got[h] for b in legal} for h in "AB"}
        best = max(legal, key=lambda b: (mean["A"][b], -b))
        rows.append({
            "n": n, "seat": seat, "hand": mine, "turned": turned, "earlier": earlier,
            "guide": observed[seat], "best": best,
            "scoreA": [mean["A"].get(b) for b in range(n + 1)],
            "scoreB": [mean["B"].get(b) for b in range(n + 1)],
            "hitB": [hits[b] / got["B"] if b in hits else None for b in range(n + 1)],
        })
    return rows


def report_oracle(rows):
    cells = defaultdict(list)
    for r in rows:
        cells[(r["n"], r["seat"])].append(r)
    print("Score = expected points for the hand, measured on opponent deals not used to pick the best bid.")
    print("'regret' = points the rule gives up against the best bid. 'same' = share of hands where they agree.\n")
    print(f"{'cards':<7}{'seat':<8}{'hands':>6}{'rule':>8}{'best':>8}{'regret':>8}{'same':>7}{'rule-best':>11}   too high by 1 / 2+, too low by 1 / 2+")
    for n in SIZES:
        for s, label in enumerate(("lead", "2nd", "dealer")):
            rs = cells.get((n, s))
            if not rs:
                continue
            m = len(rs)
            rule = sum(r["scoreB"][r["guide"]] for r in rs) / m
            best = sum(r["scoreB"][r["best"]] for r in rs) / m
            same = sum(r["guide"] == r["best"] for r in rs) / m
            diff = [r["guide"] - r["best"] for r in rs]
            avg = sum(diff) / m
            dist = (sum(d == 1 for d in diff) / m, sum(d >= 2 for d in diff) / m,
                    sum(d == -1 for d in diff) / m, sum(d <= -2 for d in diff) / m)
            print(f"{n if s == 0 else '':<7}{label:<8}{m:>6}{rule:>8.2f}{best:>8.2f}{best - rule:>8.2f}{100 * same:>6.0f}%{avg:>+11.2f}   "
                  + " / ".join(f"{100 * d:.0f}%" for d in dist))


def oracle(quick):
    rule_name = arg("--rule", "revised")
    hands_per_cell = 150 if quick else 1500
    k = 40 if quick else 120
    per_chunk = 25 if quick else 50
    chunks = hands_per_cell // per_chunk
    tasks = [(n, s, i, per_chunk, k, rule_name) for n in SIZES for s in range(3) for i in range(chunks)]
    rows = [r for part in parallel(_oracle_task, tasks) for r in part]
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, f"oracle-{rule_name}{'-quick' if quick else ''}.jsonl")
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(f"Rule '{rule_name}'. {k} opponent deals to choose the best bid and {k} fresh ones to score it, per hand.\n")
    report_oracle(rows)


# ----------------------------------------------------------- example hands

# (label, cards, turned card, seat, bids made before this player's)
EXAMPLES = [
    ("7 cards, hand 1", "AD KD 7D AS 9C 4C JH", "9D", 0, []),
    ("7 cards, hand 2", "9S 6S 2S 8H 3H 7C 5C", "9D", 0, []),
    ("7 cards, hand 3", "QD JD TD 8D 3D KS 4H", "9D", 0, []),
    ("7 cards, hand 4", "KH 5H KS QC 3C 6D 2D", "9D", 0, []),
    ("3 cards, leading", "7D AS 2H", "9D", 0, []),
    ("3 cards, leading", "KS 8C 3H", "9D", 0, []),
    ("2 cards, leading", "5D AH", "9D", 0, []),
    ("2 cards, leading", "KH 4C", "9D", 0, []),
    ("2 cards, leading", "AH 4C", "9D", 0, []),
    ("2 cards, 2nd to bid", "AH 4C", "9D", 1, [0]),
    ("1 card, leading", "AC", "9D", 0, []),
    ("1 card, 2nd to bid", "AC", "9D", 1, [0]),
]


def parse_card(text):
    return "23456789TJQKA".index(text[0]) + 13 * "CDHS".index(text[1])


def examples(quick):
    rule_name = arg("--rule", "revised")
    rule = players.RULES[rule_name]
    k = 400 if quick else 6000
    print(f"Rule '{rule_name}'. Each bid tried against {k:,} random deals of the other hands.")
    print("Earlier bidders' bids are matched when given. 'rule' marks the bid the rule gives.\n")
    for label, text, turned_text, seat, earlier in EXAMPLES:
        mine = sorted(parse_card(t) for t in text.split())
        turned = parse_card(turned_text)
        n = len(mine)
        rng = random.Random(f"example-{text}-{seat}")
        legal = [b for b in range(n + 1) if not (seat == 2 and sum(earlier) + b == n)]
        score_sum = defaultdict(float)
        hit = defaultdict(float)
        got = 0
        for _ in range(k):
            sample = _sample_opponents(rng, mine, turned, n, seat, [rule] * 3, earlier)
            if sample is None:
                continue
            tricks = _focal_outcomes(sample, turned, n, seat, earlier, None, legal, rule)
            for b, t in tricks.items():
                score_sum[b] += score(b, t)
                hit[b] += b == t
            got += 1
        rule_bid = players.bid(rule(mine, turned // 13, n, seat, earlier), n, seat, earlier)
        best = max(legal, key=lambda b: score_sum[b])
        print(f"{label}: {text}  (trump {'CDHS'[turned // 13]}, you bid {'first' if seat == 0 else 'after ' + str(earlier)})")
        for b in legal:
            tag = ("  <- rule" if b == rule_bid else "") + ("  <- best" if b == best else "")
            print(f"    bid {b}: exactly right {100 * hit[b] / got:5.1f}%   average score {score_sum[b] / got:5.2f}{tag}")
        print()


TASKS = {"unit": unit, "values": values, "guide": guide, "oracle": oracle, "examples": examples}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    if name not in TASKS:
        sys.exit(__doc__)
    TASKS[name]("--quick" in sys.argv)
