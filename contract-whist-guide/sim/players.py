"""Bidding rules.

A rule maps (hand, trump, n, seat, earlier_bids) to an estimate of the tricks
the hand will win. bid() turns an estimate into a legal bid: it rounds, then
applies the dealer's restriction.

published_guide is the advice on the page as first published on 2026-10-23,
read as literally as the prose allows. Where the prose leaves a number open,
the choice made here is flagged "reading" below. revised_guide is the advice
that replaced it.
"""
import math

from whist import ACE, KING, QUEEN, JACK


def bid(estimate, n, seat, earlier):
    """Round half down ("when torn, lean lower"), clamp, and obey the hook."""
    b = max(0, min(n, math.ceil(estimate - 0.5)))
    if seat == 2 and sum(earlier) + b == n:
        options = [x for x in (b - 1, b + 1) if 0 <= x <= n]
        b = min(options, key=lambda x: (abs(x - estimate), x))
    return b


def make_bids(hands, trump, n, rules):
    """Bid seat by seat. rules is one rule function per seat."""
    bids = []
    for seat in range(3):
        est = rules[seat](hands[seat], trump, n, seat, bids)
        bids.append(bid(est, n, seat, bids))
    return bids


def published_guide(hand, trump, n, seat, earlier):
    if n == 1:
        c = hand[0]
        return 1.0 if c // 13 == trump or c % 13 == ACE else 0.0

    trumps = [c for c in hand if c // 13 == trump]
    t = len(trumps)
    count = 0.0
    for c in hand:
        s, r = divmod(c, 13)
        if s == trump:
            if r in (ACE, KING):
                count += 1
            elif t >= 3:
                count += 0.5
            elif r in (QUEEN, JACK):
                count += 0.5
        elif r == ACE:
            count += 1
        elif r == KING:
            count += 0.5

    # Reading: "about 2 trumps in a 7-card hand, 4 or 5 is long". Scaled to
    # the hand size, and worth half a trick for each trump past (threshold - 1).
    threshold = max(2, round(n / 4) + 2)
    if t >= threshold:
        count += 0.5 * (t - (threshold - 1))

    # Reading: "short" is one or two cards in a 7-card hand, scaled down for
    # smaller hands. Two or more short side suits plus two or more trumps
    # leans up by half a trick.
    short_limit = max(1, n // 3)
    lengths = [sum(1 for c in hand if c // 13 == s) for s in range(4) if s != trump]
    if sum(1 for ln in lengths if ln <= short_limit) >= 2 and t >= 2:
        count += 0.5

    # Reading: "well under / well over" is 1.5 tricks from an even split.
    if earlier:
        gap = sum(earlier) - len(earlier) * n / 3
        if gap <= -1.5:
            count += 0.5
        elif gap >= 1.5:
            count -= 0.5

    return count


def revised_guide(hand, trump, n, seat, earlier):
    """Every trump counts 1. Side suits count by hand size:

        cards      ace    king   queen
        4 or more  3/4    1/2    1/4
        3          1/2    1/2    1/4
        2          1/2    1/2    1/4   if you lead (eldest hand)
        2          1/4    1/4    1/4   if you don't
        1          bid 1 with a trump, or with an ace, king or queen when you lead

    The estimate rounds to the nearest whole number, halves down.
    """
    if n == 1:
        c = hand[0]
        return 1.0 if c // 13 == trump or (seat == 0 and c % 13 >= QUEEN) else 0.0
    ace = 0.5 if n <= 3 else 0.75
    est = 0.0
    for c in hand:
        s, r = divmod(c, 13)
        if s == trump:
            est += 1
        elif n == 2 and seat != 0:
            est += 0.25 if r >= QUEEN else 0
        elif r == ACE:
            est += ace
        elif r == KING:
            est += 0.5
        elif r == QUEEN:
            est += 0.25
    return est


RULES = {"published": published_guide, "revised": revised_guide}
