"""Hand-built checks of the engine. Run: python3 tests.py"""
import random

import players
from whist import (ACE, JACK, KING, QUEEN, choose, deal, play_hand, score, trick_winner)

C, D, H, S = 0, 1, 2, 3


def card(s, r):
    return s * 13 + r


def test_trick_winner():
    # Diamonds trump. Clubs led. A low trump beats a club ace.
    trick = [(0, card(C, ACE)), (1, card(C, 5)), (2, card(D, 0))]
    assert trick_winner(trick, C, D) == (2, card(D, 0))
    # No trump played: the highest card of the led suit wins, off-suit loses.
    trick = [(0, card(C, 5)), (1, card(H, ACE)), (2, card(C, 9))]
    assert trick_winner(trick, C, D) == (2, card(C, 9))
    # Highest trump wins when two are played.
    trick = [(0, card(D, 3)), (1, card(D, 8)), (2, card(C, ACE))]
    assert trick_winner(trick, D, D) == (1, card(D, 8))


def test_follow_suit():
    # Holding a club, a player facing a club lead can't play the heart.
    trick = [(0, card(C, 4))]
    for greedy in (True, False):
        for bid, won in ((1, 0), (0, 0)):
            c = choose([card(C, 2), card(H, ACE)], trick, C, D, bid, won, [0, 0, 0, 0], 1, greedy)
            assert c == card(C, 2)


def test_policy_basics():
    played = [0, 0, 0, 0]
    # Needs a trick, last to play: wins with the cheapest card that does.
    trick = [(0, card(C, 8)), (1, card(C, 5))]
    hand = [card(C, 10), card(C, ACE), card(H, 2)]
    assert choose(hand, trick, C, D, 1, 0, played, 2, False) == card(C, 10)
    # Bid made, last to play, can lose: plays the highest card that loses.
    trick = [(0, card(C, 8)), (1, card(C, 9))]
    hand = [card(C, 2), card(C, 7), card(C, ACE)]
    assert choose(hand, trick, C, D, 0, 0, played, 2, False) == card(C, 7)
    # Bid made and void: sheds the highest side-suit card, keeps the trump.
    trick = [(0, card(C, 8)), (1, card(C, 9))]
    hand = [card(D, ACE), card(H, KING), card(S, 3)]
    assert choose(hand, trick, C, D, 0, 0, played, 2, False) == card(H, KING)
    # Needs a trick, void in the led suit: ruffs with a trump.
    hand = [card(D, 2), card(H, KING)]
    assert choose(hand, trick, C, D, 1, 0, played, 2, False) == card(D, 2)


def test_hook():
    # Dealer's honest estimate would make the bids total 7: moves to the nearer.
    assert players.bid(2.0, 7, 2, [3, 2]) in (1, 3)
    assert players.bid(2.2, 7, 2, [3, 2]) == 3
    assert players.bid(1.8, 7, 2, [3, 2]) == 1
    # Not the dealer: no restriction.
    assert players.bid(2.0, 7, 1, [5]) == 2
    # Round half down.
    assert players.bid(3.5, 7, 0, []) == 3
    assert players.bid(4.0, 7, 0, []) == 4


def test_totals_and_scoring():
    rng = random.Random(1)
    for n in (1, 2, 3, 5, 7):
        for _ in range(300):
            hands, turned = deal(rng, n)
            flat = [c for h in hands for c in h] + [turned]
            assert len(set(flat)) == 3 * n + 1
            trump = turned // 13
            rules = [players.published_guide] * 3
            bids = players.make_bids(hands, trump, n, rules)
            assert sum(bids) != n, (hands, turned, bids)
            won = play_hand(hands, trump, turned, bids)
            assert sum(won) == n
    assert score(3, 3) == 13 and score(0, 0) == 10 and score(2, 3) == 3


def test_guide_examples():
    """The four example hands on the page as first published (trump diamonds,
    9D turned), which the published rule reproduces."""
    def h(*cards):
        return [card(s, r) for s, r in cards]
    hand1 = h((D, ACE), (D, KING), (D, 5), (S, ACE), (C, 7), (C, 2), (H, 9))
    hand2 = h((S, 7), (S, 4), (S, 0), (H, 6), (H, 1), (C, 5), (C, 3))
    hand3 = h((D, QUEEN), (D, JACK), (D, 8), (D, 6), (D, 1), (S, KING), (H, 2))
    hand4 = h((H, KING), (H, 3), (S, KING), (C, QUEEN), (C, 1), (D, 4), (D, 0))
    got = [players.bid(players.published_guide(x, D, 7, 0, []), 7, 0, []) for x in (hand1, hand2, hand3, hand4)]
    assert got == [4, 0, 4, 1], got


def test_revised_rule():
    def h(*cards):
        return [card(s, r) for s, r in cards]
    # One card: any trump, or an ace/king/queen when leading. Otherwise 0.
    est = players.revised_guide
    assert est(h((D, 0)), D, 1, 1, [0]) == 1.0
    assert est(h((C, ACE)), D, 1, 0, []) == 1.0
    assert est(h((C, QUEEN)), D, 1, 0, []) == 1.0
    assert est(h((C, JACK)), D, 1, 0, []) == 0.0
    assert est(h((C, ACE)), D, 1, 1, [0]) == 0.0
    # Seven cards: the four example hands, trump diamonds.
    hand1 = h((D, ACE), (D, KING), (D, 5), (S, ACE), (C, 7), (C, 2), (H, 9))
    hand2 = h((S, 7), (S, 4), (S, 0), (H, 6), (H, 1), (C, 5), (C, 3))
    hand3 = h((D, QUEEN), (D, JACK), (D, 8), (D, 6), (D, 1), (S, KING), (H, 2))
    hand4 = h((H, KING), (H, 3), (S, KING), (C, QUEEN), (C, 1), (D, 4), (D, 0))
    got = [players.bid(est(x, D, 7, 0, []), 7, 0, []) for x in (hand1, hand2, hand3, hand4)]
    assert got == [4, 0, 5, 3], got
    # Two cards: a side-suit king counts 1/2 leading and 1/4 otherwise.
    assert est(h((H, KING), (C, 2)), D, 2, 0, []) == 0.5
    assert est(h((H, KING), (C, 2)), D, 2, 1, [0]) == 0.25
    # Halves round down: ace + king of side suits in a 5-card deal is 1.25.
    assert players.bid(1.5, 5, 0, []) == 1


if __name__ == "__main__":
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_")]:
        fn()
        print("ok", fn.__name__)
